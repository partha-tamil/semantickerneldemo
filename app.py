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
    json_data = list_pipelines("", "", "")

    for pipeline in json_data:
        if target_name.lower() in pipeline.name.lower():
             print(f"Found pipeline ID: {pipeline.id}")
             return str(pipeline.id)
    return "NotFound"


@kernel_function(description="Execute a azure devops pipeline based on the pipeline id")
def multi_agent_pipeline_workflow(pipeline_id: str):
   
    queued_build = execute_pipeline("", "", "", pipeline_id, parameters=None)
    if queued_build:
        print(f"Pipeline triggered successfully. Build ID: {queued_build.id}")
    else:
        print("Failed to trigger pipeline.")

@kernel_function(description="Find workflow description based on the workflow ID passed in the input ID")
def get_workflow_detail(workflow_id: str):
    ids = workflow_id
    json_data = get_workitem_details("", "", "",workitem_id= ids)

    for workflow in json_data:
        print(f"Found workflow ID: {workflow.id}")
        print(workflow.fields.get('System.Description', '').replace('<div>', '').replace('</div>', ''))
        return str(workflow.fields.get('System.Description', '').replace('<div>', '').replace('</div>', ''))
    return "NotFound"

# Replace with your OpenAI credentials
azure_endpoint = ""
azure_deployment_name = ""
azure_api_key = ""

# Initialize the kernel and AI service
kernel = Kernel()
kernel.add_function("get_id_by_name", get_id_by_name)
kernel.add_function("multi_agent_pipeline_workflow", multi_agent_pipeline_workflow),
kernel.add_function("get_workflow_detail", get_workflow_detail)
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
        "You will receive the work item description from WorkItemRetriever and retrieve the description."
        "Call get_id_by_name to retrieve the pipeline_id where name matches the work item description and pass the ID to multi_agent_pipeline_workflow to execute the pipeline."
)

workitemretriever = ChatCompletionAgent(
    kernel=kernel,
    name="WorkItemRetriever",
    instructions= "You are an Azure DevOps work item retriever assistant. "
        "You retrieve work item details based on the input prompt and the output of the function get_workitem_detail." \
        "You will pass the work item description to WorkItemAnalyser to analyze the work item and trigger the pipeline execution"
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

def get_workitem_details(org_url, pat, project_name, workitem_id):
    """
    Fetches the details of work items in the Azure DevOps project.
    """
    try:
        credentials = BasicAuthentication("", pat)
        connection = Connection(base_url=org_url, creds=credentials)
        work_item_client = connection.clients.get_work_item_tracking_client()

        work_items = work_item_client.get_work_items(project=project_name, ids=[workitem_id])
        print("\nAvailable Work Items:")
        for work_item in work_items:
            print(f"ID: {work_item.id}, Title: {work_item.fields['System.Title']}, "
                  f"Description: {work_item.fields.get('System.Description', '').replace('<div>', '').replace('</div>', '')}")
        return work_items

    except Exception as e:
        print(f"Error fetching work items: {e}")
        return []


async def automated_devops_workflow(workitem: str):
    
    workitemretriever_chat = ChatHistory()
    print(f"\n🔍 Retrieving work item: {workitem}")
    workitemretriever_chat.add_user_message(f"Retrieve the work item: {workitem}")
    async for workitem_response in workitemretriever.invoke(workitemretriever_chat):
        workitemretrieverresponse = workitem_response
        print   (workitemretrieverresponse.content,end="")
   
    workitem_chat = ChatHistory()
    print(f"\n🔍 Analyzing work item: {workitem}")
    workitem_chat.add_user_message(f"Analyze the work item: {workitem}")
    async for workitem_response1 in workitemanalyser.invoke(workitem_chat):
        workitem_chat_response = workitem_response1
        print(workitem_chat_response.content,end="")

# Run the workflow
if __name__ == "__main__":
    asyncio.run(automated_devops_workflow(""))
