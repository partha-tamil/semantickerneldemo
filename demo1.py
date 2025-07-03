from azure.devops.v7_1.release.models import ReleaseStartMetadata
from azure.devops.v7_1.build.models import Build
from azure.devops.v7_1.release.models import ArtifactMetadata

# --- Add Pipeline Execution Functions ---

async def list_pipelines(org_url, pat, project_name):
    """
    Fetches the list of pipelines in the Azure DevOps project.
    """
    try:
        credentials = BasicAuthentication("", pat)
        connection = Connection(base_url=org_url, creds=credentials)
        build_client = connection.clients.get_build_client()

        pipelines = await build_client.get_definitions(project=project_name)
        print("\nAvailable Pipelines:")
        for pipeline in pipelines:
            print(f"ID: {pipeline.id}, Name: {pipeline.name}")
        return pipelines

    except Exception as e:
        print(f"Error fetching pipelines: {e}")
        return []

async def execute_pipeline(org_url, pat, project_name, pipeline_id, parameters=None):
    """
    Executes a pipeline by its ID in the Azure DevOps project.
    """
    try:
        credentials = BasicAuthentication("", pat)
        connection = Connection(base_url=org_url, creds=credentials)
        build_client = connection.clients.get_build_client()

        build = Build(definition={"id": pipeline_id}, parameters=parameters)
        queued_build = await build_client.queue_build(build=build, project=project_name)
        print(f"Pipeline '{pipeline_id}' triggered successfully. Build ID: {queued_build.id}")
        return queued_build

    except Exception as e:
        print(f"Error triggering pipeline: {e}")
        return None

# --- Modify the Agent Workflow ---

async def multi_agent_pipeline_workflow(topic: str):
    """
    Modified workflow to include pipeline execution.
    """
    # Step 1: List Pipelines
    print("\n--- Fetching Pipelines ---")
    pipelines = await list_pipelines(AZURE_DEVOPS_ORG_URL, AZURE_DEVOPS_PAT, AZURE_DEVOPS_PROJECT_NAME)
    if not pipelines:
        print("No pipelines found.")
        return

    # Step 2: Get User Input for Pipeline Selection
    pipeline_id = None
    while not pipeline_id:
        try:
            pipeline_id = int(input("\nEnter the Pipeline ID to execute: "))
            if pipeline_id not in [pipeline.id for pipeline in pipelines]:
                print("Invalid Pipeline ID. Please try again.")
                pipeline_id = None
        except ValueError:
            print("Invalid input. Please enter a numeric Pipeline ID.")

    # Step 3: Trigger the Selected Pipeline
    print("\n--- Triggering Pipeline ---")
    parameters = {"topic": topic}  # Example: Pass topic as a parameter to the pipeline
    queued_build = await execute_pipeline(AZURE_DEVOPS_ORG_URL, AZURE_DEVOPS_PAT, AZURE_DEVOPS_PROJECT_NAME, pipeline_id, parameters)
    if queued_build:
        print(f"Pipeline triggered successfully. Build ID: {queued_build.id}")
    else:
        print("Failed to trigger pipeline.")

# --- Run the Modified Workflow ---
if __name__ == "__main__":
    asyncio.run(multi_agent_pipeline_workflow("Write a Python function to calculate the factorial of a number"))