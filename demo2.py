import asyncio
import os
import json
import base64
import httpx # For making HTTP requests to Azure DevOps API

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import (
    AzureChatCompletion,
    OpenAIChatCompletion,
)
from semantic_kernel.functions import kernel_function
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.contents.chat_history import ChatHistory

# --- Configuration for Azure DevOps ---
AZURE_DEVOPS_ORG = os.getenv("AZURE_DEVOPS_ORG")
AZURE_DEVOPS_PROJECT = os.getenv("AZURE_DEVOPS_PROJECT")
AZURE_DEVOPS_PAT = os.getenv("AZURE_DEVOPS_PAT") # Personal Access Token

# --- Azure DevOps Plugin ---
class AzureDevOpsPlugin:
    def __init__(self, org, project, pat):
        if not all([org, project, pat]):
            raise ValueError("Azure DevOps organization, project, and PAT must be set as environment variables.")
        self.base_url = f"https://dev.azure.com/{org}/{project}/_apis"
        self.headers = {
            "Authorization": f"Basic {base64.b64encode(f':{pat}'.encode()).decode()}",
            "Content-Type": "application/json",
        }

    @kernel_function(
        description="Gets details of an Azure DevOps work item.",
        name="get_work_item_details",
    )
    async def get_work_item_details(self, work_item_id: str) -> str:
        """
        Retrieves the title and description of an Azure DevOps work item.
        """
        url = f"{self.base_url}/wit/workitems/{work_item_id}?api-version=7.1"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status() # Raise an exception for HTTP errors
                data = response.json()
                title = data.get("fields", {}).get("System.Title", "N/A")
                description = data.get("fields", {}).get("System.Description", "N/A")
                return json.dumps({"title": title, "description": description})
        except httpx.HTTPStatusError as e:
            return f"Error fetching work item {work_item_id}: {e.response.status_code} - {e.response.text}"
        except Exception as e:
            return f"An unexpected error occurred: {str(e)}"

    @kernel_function(
        description="Executes an Azure DevOps pipeline.",
        name="execute_pipeline",
    )
    async def execute_pipeline(self, pipeline_id: str, pipeline_name: str, parameters: str = "{}") -> str:
        """
        Triggers an Azure DevOps pipeline run.
        Parameters should be a JSON string of key-value pairs for pipeline variables.
        """
        url = f"{self.base_url}/pipelines/{pipeline_id}/runs?api-version=7.1-preview.1"
        payload = {
            "resources": {
                "repositories": {
                    "self": {
                        "refName": "refs/heads/main" # Assuming 'main' branch, adjust if needed
                    }
                }
            },
            "templateParameters": json.loads(parameters) # For YAML pipeline template parameters
        }
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=self.headers, json=payload)
                response.raise_for_status()
                run_data = response.json()
                run_url = run_data.get("_links", {}).get("web", {}).get("href", "N/A")
                return f"Successfully triggered pipeline '{pipeline_name}' (ID: {pipeline_id}). Run URL: {run_url}"
        except httpx.HTTPStatusError as e:
            return f"Error executing pipeline {pipeline_name} (ID: {pipeline_id}): {e.response.status_code} - {e.response.text}"
        except json.JSONDecodeError:
            return f"Invalid JSON for parameters: {parameters}"
        except Exception as e:
            return f"An unexpected error occurred: {str(e)}"

# --- Main Semantic Kernel Logic ---
async def main():
    kernel = Kernel()

    # Configure AI Service
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        kernel.add_service(
            OpenAIChatCompletion(service_id="default", ai_model_id="gpt-4o") # Using gpt-4o for better reasoning
        )
        print("Using OpenAI GPT-4o")
    else:
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        azure_deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
        azure_api_key = os.getenv("AZURE_OPENAI_API_KEY")

        if azure_endpoint and azure_deployment_name and azure_api_key:
            kernel.add_service(
                AzureChatCompletion(
                    service_id="default",
                    deployment_name=azure_deployment_name,
                    endpoint=azure_endpoint,
                    api_key=azure_api_key,
                )
            )
            print(f"Using Azure OpenAI with deployment: {azure_deployment_name}")
        else:
            print("Please set your OpenAI or Azure OpenAI environment variables.")
            return

    # Create and import the Azure DevOps plugin
    try:
        azure_devops_plugin = AzureDevOpsPlugin(
            AZURE_DEVOPS_ORG, AZURE_DEVOPS_PROJECT, AZURE_DEVOPS_PAT
        )
        kernel.add_plugin(azure_devops_plugin, plugin_name="AzureDevOps")
        print("AzureDevOps plugin loaded.")
    except ValueError as e:
        print(f"Failed to load AzureDevOps plugin: {e}")
        return

    # Define the Agent with instructions and tool calling enabled
    agent = ChatCompletionAgent(
        service_id="default",
        kernel=kernel,
        name="DevOps-Orchestrator",
        instructions=(
            "You are an Azure DevOps pipeline orchestrator. Your task is to interpret user requests "
            "related to work items and pipeline execution. "
            "When a user provides a work item ID and asks for VM or database provisioning, "
            "you must first use the `get_work_item_details` tool to understand the work item. "
            "Then, you should identify which specific Azure DevOps pipelines are needed to fulfill the request. "
            "For creating a Virtual Machine, use pipeline ID '123' and name 'VM-Provisioning-Pipeline'. " # **REPLACE WITH YOUR ACTUAL PIPELINE ID/NAME**
            "For creating a Database, use pipeline ID '456' and name 'DB-Creation-Pipeline'. "     # **REPLACE WITH YOUR ACTUAL PIPELINE ID/NAME**
            "If the work item details include specific parameters (e.g., 'VM_SIZE: Standard_D2s_v3'), "
            "pass them as JSON to the `execute_pipeline` tool. "
            "Always confirm with the user before executing a pipeline. "
            "If successful, provide the pipeline run URL. If not, explain the error. "
            "If you cannot determine the pipeline, ask for clarification. "
            "Be concise and helpful."
        ),
    )

    chat_history = ChatHistory()

    print("\nDevOps Orchestrator Agent (type 'exit' to quit)\n")
    print("Example: 'For work item 789, please provision a virtual machine and a SQL database.'")
    print("Example: 'Execute VM provisioning for work item 12345, with VM_SIZE as Standard_B2ms'")
    print("Example: 'What is work item 12345 about?'")

    while True:
        user_input = input("User > ")
        if user_input.lower() == "exit":
            break

        chat_history.add_user_message(user_input)

        # Invoke the agent. Semantic Kernel will handle tool calling based on the prompt.
        response = await agent.invoke(chat_history)

        print(f"Orchestrator > {response.content}")
        chat_history.add_assistant_message(response.content)

if __name__ == "__main__":
    # Set your environment variables before running:
    # export OPENAI_API_KEY="YOUR_OPENAI_API_KEY"
    # OR
    # export AZURE_OPENAI_ENDPOINT="YOUR_AZURE_OPENAI_ENDPOINT"
    # export AZURE_OPENAI_DEPLOYMENT_NAME="YOUR_AZURE_OPENAI_DEPLOYMENT_NAME"
    # export AZURE_OPENAI_API_KEY="YOUR_AZURE_OPENAI_API_KEY"
    #
    # export AZURE_DEVOPS_ORG="your-azure-devops-organization-name"
    # export AZURE_DEVOPS_PROJECT="your-azure-devops-project-name"
    # export AZURE_DEVOPS_PAT="YOUR_AZURE_DEVOPS_PAT" # Make sure this PAT has necessary permissions

    asyncio.run(main())
