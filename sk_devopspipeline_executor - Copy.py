import asyncio
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.contents.chat_history import ChatHistory
from azure.devops.v7_1.release.models import ReleaseStartMetadata
from azure.devops.v7_1.build.models import Build
from azure.devops.v7_1.release.models import ArtifactMetadata
import azure.devops.v7_1.release.models as release_models
from azure.devops.connection import Connection
from azure.devops.credentials import BasicAuthentication
import asyncio, json
from semantic_kernel.connectors.ai.open_ai import (
    AzureChatCompletion,
    OpenAIChatCompletion,
)

from semantic_kernel.functions import kernel_function


@kernel_function(description="Find pipeline ID based on pipeline description.")
def get_id_by_name(target_name):
    """
    Parses JSON to find the ID where Name matches the target_name.
    """
    json_data = list_pipelines("")

    for pipeline in json_data:
        if target_name.lower() in pipeline.name.lower():
             print(f"Found pipeline ID: {pipeline.id}")
             return str(pipeline.id)
    return "NotFound"


@kernel_function(description="Execute a azure devops pipeline based on the pipeline id")
def multi_agent_pipeline_workflow(pipeline_id: str):
   
    queued_build = execute_pipeline("", pipeline_id, parameters=None)
    if queued_build:
        print(f"Pipeline triggered successfully. Build ID: {queued_build.id}")
    else:
        print("Failed to trigger pipeline.")



# Replace with your OpenAI credentials
azure_endpoint = "/"
azure_deployment_name = ""
azure_api_key = ""

# Initialize the kernel and AI service
kernel = Kernel()
kernel.add_function("get_id_by_name", get_id_by_name)
kernel.add_function("multi_agent_pipeline_workflow", multi_agent_pipeline_workflow)
kernel.add_service(
                AzureChatCompletion(
                    deployment_name=azure_deployment_name,
                    endpoint=azure_endpoint,
                    api_key=azure_api_key,
                )
            )

# Define agent roles
workitemanalyser = ChatCompletionAgent(
    kernel=kernel,
    name="WorkItemAnalyser",
    instructions= "You are an Azure DevOps work item analyzer assistant. "
        "You analyze the input prompt and list of available pipelines. "
        "Call get_id_by_name to retrieve the pipeline_id where name matches the work item intent and pass the ID to multi_agent_pipeline_workflow to execute the pipeline."
)

def list_pipelines(org_url, pat, project_name):
    """
    Fetches the list of pipelines in the Azure DevOps project.
    """
    try:
        credentials = BasicAuthentication("", pat)
        connection = Connection(base_url=org_url, creds=credentials)
        build_client = connection.clients.get_build_client()

        pipelines = build_client.get_definitions(project=project_name)
        print("\nAvailable Pipelines:")
        for pipeline in pipelines:
            print(f"ID: {pipeline.id}, Name: {pipeline.name}")
        return pipelines

    except Exception as e:
        print(f"Error fetching pipelines: {e}")
        return []

def execute_pipeline(org_url, pat, project_name, pipeline_id, parameters=None):
    """
    Executes a pipeline by its ID in the Azure DevOps project.
    """
    try:
        credentials = BasicAuthentication("", pat)
        connection = Connection(base_url=org_url, creds=credentials)
        build_client = connection.clients.get_build_client()

        build = Build(definition={"id": pipeline_id}, parameters=parameters)
        queued_build = build_client.queue_build(build=build, project=project_name)
        print(f"Pipeline '{pipeline_id}' triggered successfully. Build ID: {queued_build.id}")
        return queued_build

    except Exception as e:
        print(f"Error triggering pipeline: {e}")
        return None

# --- Modify the Agent Workflow ---



async def multi_agent_workflow(topic: str):
    # Step 1: WorkItemAnalyser analyzes the work item
    
    # id = get_id_by_name(topic)
    # multi_agent_pipeline_workflow(id)
    workitem_chat = ChatHistory()
    print(f"\n🔍 Analyzing work item for topic: {topic}")
    workitem_chat.add_user_message(f"Analyze the work item for the topic: {topic}")
    async for workitem_response in workitemanalyser.invoke(workitem_chat):
        pass

# Run the workflow
if __name__ == "__main__":
    asyncio.run(multi_agent_workflow("virtual machine"))