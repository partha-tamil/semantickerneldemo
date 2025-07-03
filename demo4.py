import azure.functions as func
import azure.durable_functions as df
import logging
import json
import os
import asyncio
from datetime import datetime

# Import Semantic Kernel and Azure DevOps related modules
# We will initialize Kernel and agents within the activity functions as needed,
# or pass necessary configurations.
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.functions import kernel_function

# Azure DevOps imports (assuming these are in a utility file or will be placed in activity)
from azure.devops.connection import Connection
from azure.devops.credentials import BasicAuthentication
from azure.devops.v7_1.build.models import Build
# from azure.devops.v7_1.release.models import ReleaseStartMetadata, ArtifactMetadata, release_models # Not used in provided code

# Create a Durable Functions Blueprint
bp = df.Blueprint()

app = func.FunctionApp() # Initialize app at the top

# --- HTTP Starter Function ---
@app.route(route="start_devops_workflow", methods=["POST"])
@app.durable_client_input(client_name="client")
async def http_start_devops_workflow(req: func.HttpRequest, client: df.DurableOrchestrationClient) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request to start DevOps workflow.')

    try:
        req_body = req.get_json()
        workitem = req_body.get('workitem') # Renamed 'name' to 'workitem' for clarity
    except ValueError:
        return func.HttpResponse(
            "Please pass a 'workitem' in the request body (JSON format).",
            status_code=400
        )

    if not workitem:
        return func.HttpResponse(
            "Please pass a 'workitem' in the request body.",
            status_code=400
        )

    # Start the orchestrator function
    instance_id = await client.start_new_orchestration("orchestrate_automated_devops", workitem)

    logging.info(f"Started orchestration with ID = '{instance_id}'.")

    # Return status URLs to the client immediately
    return client.create_check_status_response(req, instance_id)

# --- Orchestrator Function ---
@bp.orchestration_trigger(context_name="context")
def orchestrate_automated_devops(context: df.DurableOrchestrationContext):
    logging.info("Orchestrator function 'orchestrate_automated_devops' started.")
    workitem_input = context.get_input()

    # Call Activity Function 1: Retrieve Work Item
    logging.info(f"Calling activity to retrieve work item: {workitem_input}")
    retrieved_description = yield context.call_activity("Activity_RetrieveWorkItem", workitem_input)
    logging.info(f"Retrieved Work Item Description: {retrieved_description}")

    if retrieved_description == "NotFound" or not retrieved_description:
        logging.warning(f"Work item description not found for: {workitem_input}")
        return {"status": "Failed", "message": f"Work item description not found for: {workitem_input}"}

    # Call Activity Function 2: Analyze Work Item and Find Pipeline ID
    logging.info(f"Calling activity to analyze work item and find pipeline ID for description: {retrieved_description}")
    pipeline_id = yield context.call_activity("Activity_AnalyzeWorkItemAndFindPipeline", retrieved_description)
    logging.info(f"Found Pipeline ID: {pipeline_id}")

    if pipeline_id == "NotFound" or not pipeline_id:
        logging.warning(f"Pipeline ID not found for description: {retrieved_description}")
        return {"status": "Failed", "message": f"Pipeline ID not found for description: {retrieved_description}"}

    # Call Activity Function 3: Execute Pipeline
    logging.info(f"Calling activity to execute pipeline with ID: {pipeline_id}")
    execution_result = yield context.call_activity("Activity_ExecutePipeline", pipeline_id)
    logging.info(f"Pipeline execution result: {execution_result}")

    return {"status": "Completed", "result": execution_result}

# --- Activity Functions ---

# Helper function to initialize Kernel (moved here to avoid global state issues and for clarity)
# This will be called within each activity that needs the kernel.
def _initialize_kernel_and_agents():
    kernel = Kernel()
    kernel.add_service(
        AzureChatCompletion(
            deployment_name=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
            endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        )
    )

    # Re-define your kernel functions
    @kernel_function(description="Find pipeline ID based on pipeline description.")
    def get_id_by_name(target_name):
        json_data = _list_pipelines() # Use the internal helper
        for pipeline in json_data:
            if target_name.lower() in pipeline.name.lower():
                 logging.info(f"Found pipeline ID: {pipeline.id} for target: {target_name}")
                 return str(pipeline.id)
        logging.info(f"Pipeline ID 'NotFound' for target: {target_name}")
        return "NotFound"

    @kernel_function(description="Execute an Azure DevOps pipeline based on the pipeline id")
    def multi_agent_pipeline_workflow(pipeline_id: str):
        queued_build = _execute_pipeline(pipeline_id) # Use the internal helper
        if queued_build:
            logging.info(f"Pipeline triggered successfully. Build ID: {queued_build.id}")
            return f"Pipeline triggered successfully. Build ID: {queued_build.id}"
        else:
            logging.error("Failed to trigger pipeline.")
            return "Failed to trigger pipeline."

    @kernel_function(description="Find workflow description based on the workflow ID passed in the input ID")
    def get_workflow_detail(workflow_id: str):
        json_data = _get_workitem_details(workflow_id=workflow_id) # Use the internal helper
        for workflow in json_data:
            desc = workflow.fields.get('System.Description', '').replace('<div>', '').replace('</div>', '')
            logging.info(f"Found workflow ID: {workflow.id}, Description: {desc}")
            return desc
        logging.info(f"Workflow description 'NotFound' for ID: {workflow_id}")
        return "NotFound"

    kernel.add_function("get_id_by_name", get_id_by_name)
    kernel.add_function("multi_agent_pipeline_workflow", multi_agent_pipeline_workflow)
    kernel.add_function("get_workflow_detail", get_workflow_detail)

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
    return kernel, workitemanalyser, workitemretriever

# Helper functions for Azure DevOps interaction (encapsulated)
def _get_azure_devops_connection():
    org_url = os.getenv("AZURE_DEVOPS_ORG_URL")
    pat = os.getenv("AZURE_DEVOPS_PAT")
    if not org_url or not pat:
        raise ValueError("Azure DevOps URL or PAT not set in environment variables.")
    credentials = BasicAuthentication("", pat)
    return Connection(base_url=org_url, creds=credentials)

def _list_pipelines():
    project_name = os.getenv("AZURE_DEVOPS_PROJECT_NAME")
    try:
        connection = _get_azure_devops_connection()
        build_client = connection.clients.get_build_client()
        pipelines = build_client.get_definitions(project=project_name)
        logging.info(f"Fetched {len(pipelines)} pipelines.")
        return pipelines
    except Exception as e:
        logging.error(f"Error fetching pipelines: {e}")
        return []

def _execute_pipeline(pipeline_id: str, parameters=None):
    project_name = os.getenv("AZURE_DEVOPS_PROJECT_NAME")
    try:
        connection = _get_azure_devops_connection()
        build_client = connection.clients.get_build_client()
        build = Build(definition={"id": pipeline_id}, parameters=parameters)
        queued_build = build_client.queue_build(build=build, project=project_name)
        logging.info(f"Pipeline '{pipeline_id}' triggered. Build ID: {queued_build.id}")
        return {"id": queued_build.id, "url": queued_build.url} # Return essential info
    except Exception as e:
        logging.error(f"Error triggering pipeline {pipeline_id}: {e}")
        return None

def _get_workitem_details(workitem_id: str):
    project_name = os.getenv("AZURE_DEVOPS_PROJECT_NAME")
    try:
        connection = _get_azure_devops_connection()
        work_item_client = connection.clients.get_work_item_tracking_client()
        work_items = work_item_client.get_work_items(project=project_name, ids=[int(workitem_id)])
        logging.info(f"Fetched {len(work_items)} work items for ID: {workitem_id}")
        return work_items
    except Exception as e:
        logging.error(f"Error fetching work items for ID {workitem_id}: {e}")
        return []


# Activity 1: Retrieve Work Item Description
@bp.activity_trigger(input_name="workitem_id")
async def Activity_RetrieveWorkItem(workitem_id: str):
    logging.info(f"Activity_RetrieveWorkItem started for ID: {workitem_id}")
    kernel, workitemanalyser, workitemretriever = _initialize_kernel_and_agents()

    # Original logic from automated_devops_workflow
    workitemretriever_chat = ChatHistory()
    workitemretriever_chat.add_user_message(f"Retrieve the work item with ID: {workitem_id}")
    # The actual retrieval happens via the get_workflow_detail function
    # which is bound to the kernel and is implicitly called by the agent.
    
    # We need to explicitly call get_workflow_detail here if it's the direct source.
    # If the agent is smart enough to call it, then the agent's invoke would work.
    # For now, let's assume the agent uses it correctly or we call it directly.

    # Option A: Rely on agent to call get_workflow_detail
    # response_stream = workitemretriever.invoke(workitemretriever_chat)
    # async for response in response_stream:
    #     logging.info(f"WorkItemRetriever response content: {response.content}")
    #     # Extract the relevant part, this needs careful parsing if agent output is complex
    #     # For now, let's assume get_workflow_detail is called and its result is returned
    #     # by the agent, or we call it directly.

    # Simpler: Directly call the underlying function if it's meant for direct use
    description = _get_workitem_details(workitem_id)
    if description:
        return description[0].fields.get('System.Description', '').replace('<div>', '').replace('</div>', '')
    else:
        return "NotFound"


# Activity 2: Analyze Work Item and Find Pipeline ID
@bp.activity_trigger(input_name="workitem_description")
async def Activity_AnalyzeWorkItemAndFindPipeline(workitem_description: str):
    logging.info(f"Activity_AnalyzeWorkItemAndFindPipeline started for description: {workitem_description}")
    kernel, workitemanalyser, workitemretriever = _initialize_kernel_and_agents()

    # Original logic from automated_devops_workflow (part that uses workitemanalyser)
    workitem_chat = ChatHistory()
    workitem_chat.add_user_message(f"Analyze the work item description: '{workitem_description}' and find the relevant pipeline ID. Then prepare to trigger it.")

    # The agent will call get_id_by_name and multi_agent_pipeline_workflow
    # We need to capture the *result* of the agent's action, specifically the pipeline ID found.
    # The agent's response might be text, so we need to parse it or make the agent return structured data.

    # A more robust way might be for the agent to return the pipeline ID explicitly,
    # or for this activity to simply call `get_id_by_name` directly if the agent's role is just to decide.
    
    # Let's directly use the kernel function for clarity in the Durable context
    # as the agent's primary role in the original code was to orchestrate these functions.
    # We will pass the description to get_id_by_name.
    # The agent's instructions are "Call get_id_by_name to retrieve the pipeline_id where name matches the work item description"
    # So the agent itself is meant to produce the ID.

    # Simulating agent's behavior to get the ID
    response_stream = workitemanalyser.invoke(workitem_chat)
    pipeline_id = "NotFound"
    async for response in response_stream:
        # The agent's response could be varied. We need to extract the pipeline ID.
        # This is a critical point: how does your agent communicate the ID back?
        # A simple approach: agent prints/returns the ID as a string that we can parse.
        # For a robust solution, you might need Semantic Kernel's FunctionCall or structured output.
        logging.info(f"WorkItemAnalyser response content: {response.content}")
        
        # Simple heuristic: look for a number in the response that looks like a pipeline ID
        # This part might need refinement based on actual agent output.
        if "pipeline id:" in response.content.lower():
            try:
                # Assuming the agent explicitly states "Pipeline ID: 12345"
                start_index = response.content.lower().find("pipeline id:") + len("pipeline id:")
                end_index = response.content.find(" ", start_index) # Find next space
                if end_index == -1: # If ID is at the end of the string
                    end_index = len(response.content)
                
                potential_id = response.content[start_index:end_index].strip()
                if potential_id.isdigit():
                    pipeline_id = potential_id
                    break # Found the ID, no need to process further responses

            except Exception as e:
                logging.warning(f"Could not parse pipeline ID from agent response: {e}")
        elif response.content.strip().isdigit(): # If the agent simply returns the ID
             pipeline_id = response.content.strip()
             break

    return pipeline_id

# Activity 3: Execute Pipeline
@bp.activity_trigger(input_name="pipeline_id")
async def Activity_ExecutePipeline(pipeline_id: str):
    logging.info(f"Activity_ExecutePipeline started for ID: {pipeline_id}")
    # The agent's multi_agent_pipeline_workflow function is meant to execute the pipeline.
    # We can directly call the underlying helper here.
    # If the agent is expected to make the call based on instructions, you'd involve the kernel here too.
    
    # For now, let's call the internal helper function
    result = _execute_pipeline(pipeline_id)
    if result:
        return f"Pipeline {pipeline_id} queued successfully. Build ID: {result['id']}"
    else:
        return f"Failed to queue pipeline {pipeline_id}."

# Register the Durable Functions blueprint with the main Function App
app.register_blueprint(bp)
