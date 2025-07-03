import asyncio
import os
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import (
    AzureChatCompletion,
    OpenAIChatCompletion,
)
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.contents.chat_history import ChatHistory

# Import Azure DevOps libraries
from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication
from azure.devops.v7_1.git.models import GitPush, GitRefUpdate, GitCommitRef, ItemContent, ItemContentType

# --- Azure OpenAI Credentials (Replace with your actual values) ---
# If using OpenAI directly, uncomment and set OPENAI_API_KEY
# OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Azure OpenAI credentials
azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "YOUR_AZURE_OPENAI_ENDPOINT") # e.g., "https://your-resource-name.openai.azure.com/"
azure_deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "YOUR_AZURE_OPENAI_DEPLOYMENT_NAME") # e.g., "gpt-4"
azure_api_key = os.getenv("AZURE_OPENAI_API_KEY", "YOUR_AZURE_OPENAI_API_KEY")

# --- Azure DevOps Credentials (Replace with your actual values) ---
AZURE_DEVOPS_ORG_URL = os.getenv("AZURE_DEVOPS_ORG_URL", "https://dev.azure.com/YOUR_ORGANIZATION") # e.g., "https://dev.azure.com/YourOrgName"
AZURE_DEVOPS_PAT = os.getenv("AZURE_DEVOPS_PAT", "YOUR_PERSONAL_ACCESS_TOKEN") # Your PAT generated in Azure DevOps
AZURE_DEVOPS_PROJECT_NAME = os.getenv("AZURE_DEVOPS_PROJECT_NAME", "YOUR_PROJECT_NAME") # e.g., "MyCloudProject"
AZURE_DEVOPS_REPO_NAME = os.getenv("AZURE_DEVOPS_REPO_NAME", "YOUR_REPO_NAME") # e.g., "MyPythonRepo"
TARGET_FILE_PATH = "generated_code/factorial_function.py" # Path within your repo to save the file
COMMIT_AUTHOR_NAME = "Your Name"
COMMIT_AUTHOR_EMAIL = "your.email@example.com"
TARGET_BRANCH = "main" # Or 'master', depending on your repository's default branch

# Initialize the kernel and AI service
kernel = Kernel()
# Ensure you are using AzureChatCompletion if you have Azure OpenAI setup
kernel.add_service(
    AzureChatCompletion(
        deployment_name=azure_deployment_name,
        endpoint=azure_endpoint,
        api_key=azure_api_key,
    )
)

# Define agent roles
coder = ChatCompletionAgent(
    kernel=kernel,
    name="Coder",
    instructions="You are a coding assistant. Provide code snippets and explanations for programming tasks."
)

codereviewer = ChatCompletionAgent(
    kernel=kernel,
    name="CodeReviewer",
    instructions="You are a code reviewer. Use the code provided to critique and improve the implementation." \
    " Give final approved code. Start with 'Approved Code:' and end with 'End of approved Code.'\n\nExample:\n\nApproved Code:\n```Your code here\n```\n\nEnd of approved Code."
)

async def get_repo_id(git_client, project_name, repo_name):
    """Fetches the repository ID from its name."""
    try:
        repos = await git_client.get_repositories(project=project_name)
        for repo in repos:
            if repo.name == repo_name:
                return repo.id
        print(f"Error: Repository '{repo_name}' not found in project '{project_name}'.")
        return None
    except Exception as e:
        print(f"Error fetching repository ID: {e}")
        return None

async def get_latest_commit_id(git_client, project_id, repo_id, branch_name):
    """Fetches the latest commit ID for a given branch."""
    try:
        # Get the ref for the target branch
        refs = await git_client.get_refs(
            repository_id=repo_id,
            project=project_id,
            filter=f"heads/{branch_name}"
        )
        if refs:
            return refs[0].object_id
        return None
    except Exception as e:
        print(f"Error getting latest commit ID for branch {branch_name}: {e}")
        return None

async def commit_to_azure_devops(
    file_path: str,
    file_content: str,
    commit_message: str,
    org_url: str,
    pat: str,
    project_name: str,
    repo_name: str,
    author_name: str,
    author_email: str,
    branch_name: str = "main"
):
    """
    Commits a file to an Azure DevOps Git repository.
    If the file exists, it will update it. If not, it will create it.
    """
    try:
        # Create a connection to the Azure DevOps organization
        credentials = BasicAuthentication("", pat)
        connection = Connection(base_url=org_url, creds=credentials)
        git_client = connection.clients.get_git_client()

        # Get project and repository IDs
        project = await connection.clients.get_core_client().get_project(project_name)
        project_id = project.id
        repo_id = await get_repo_id(git_client, project_name, repo_name)

        if not repo_id:
            return False

        # Get the latest commit ID of the target branch
        old_object_id = await get_latest_commit_id(git_client, project_id, repo_id, branch_name)

        # Prepare the file content
        item_content = ItemContent(content=file_content, content_type=ItemContentType.RAWTEXT)

        # Create a GitChange object
        # If old_object_id exists, it's an update, otherwise it's an add
        change_type = "edit" if old_object_id else "add" # Assuming 'edit' if branch exists, 'add' if new file
        
        # Check if the file already exists in the repo
        try:
            item = await git_client.get_item(
                repository_id=repo_id,
                path=file_path,
                project=project_id,
                include_content=False,
                version_descriptor={"versionType": "branch", "version": branch_name}
            )
            # If item is found, it's an edit
            change_type = "edit"
        except Exception as e:
            # If item is not found, it's an add
            if "TF401019" in str(e): # Specific error for file not found
                change_type = "add"
            else:
                print(f"Error checking file existence: {e}")
                return False


        git_change = {
            "change_type": change_type,
            "item": {"path": file_path},
            "new_content": item_content,
        }

        # Create a GitCommitRef object
        git_commit = GitCommitRef(
            comment=commit_message,
            changes=[git_change],
            author={"name": author_name, "email": author_email},
            committer={"name": author_name, "email": author_email},
        )

        # Create a GitRefUpdate object for the target branch
        ref_update = GitRefUpdate(
            name=f"refs/heads/{branch_name}",
            old_object_id=old_object_id if old_object_id else "0000000000000000000000000000000000000000", # Use zero ID for new branch/first commit
            new_object_id="" # This will be filled by the API
        )

        # Create a GitPush object
        git_push = GitPush(
            ref_updates=[ref_update],
            commits=[git_commit],
        )

        # Perform the push
        push_result = await git_client.create_push(
            git_push_to_create=git_push,
            repository_id=repo_id,
            project=project_id
        )

        print(f"Successfully committed to Azure DevOps Repo '{repo_name}' in project '{project_name}'.")
        print(f"Commit ID: {push_result.commits[0].commit_id}")
        return True

    except Exception as e:
        print(f"Failed to commit to Azure DevOps: {e}")
        return False


async def multi_agent_workflow(topic: str):
    # Step 1: Coder writes code
    code_chat = ChatHistory()
    code_chat.add_user_message(f"Write code for the topic: {topic}")
    print("\n--- Coder is generating code ---")
    code_response = None
    async for response_chunk in coder.invoke(code_chat):
        code_response = response_chunk # Get the full response
        print(response_chunk.content, end="") # Print chunks as they arrive
    print("\n--- Code Generation Complete ---")

    if not code_response or not code_response.content:
        print("Coder failed to generate code.")
        return

    # Step 2: CodeReviewer critiques the implementation
    reviewer_chat = ChatHistory()
    reviewer_chat.add_user_message(f"Based on this code, provide a critique and suggest improvements:\n{code_response.content}")
    print("\n--- Code Reviewer is reviewing code ---")
    reviewer_response = None
    async for response_chunk in codereviewer.invoke(reviewer_chat):
        reviewer_response = response_chunk # Get the full response
        print(response_chunk.content, end="") # Print chunks as they arrive
    print("\n--- Code Review Complete ---")

    if not reviewer_response or not reviewer_response.content:
        print("Code reviewer failed to provide feedback.")
        return

    # Step 3: Extract approved code and commit to Azure DevOps
    approved_code_content = ""
    response_text = reviewer_response.content
    start_tag = "Approved Code:\n```"
    end_tag = "```\n\nEnd of approved Code."

    start_index = response_text.find(start_tag)
    if start_index != -1:
        start_index += len(start_tag)
        end_index = response_text.find(end_tag, start_index)
        if end_index != -1:
            approved_code_content = response_text[start_index:end_index].strip()
            print("\n--- Extracted Approved Code ---")
            print(approved_code_content)
        else:
            print(f"Warning: Could not find '{end_tag}' in reviewer response.")
    else:
        print(f"Warning: Could not find '{start_tag}' in reviewer response.")

    if approved_code_content:
        commit_message = f"Add/Update {os.path.basename(TARGET_FILE_PATH)} for '{topic}'"
        print(f"\nAttempting to commit code to Azure DevOps...")
        success = await commit_to_azure_devops(
            file_path=TARGET_FILE_PATH,
            file_content=approved_code_content,
            commit_message=commit_message,
            org_url=AZURE_DEVOPS_ORG_URL,
            pat=AZURE_DEVOPS_PAT,
            project_name=AZURE_DEVOPS_PROJECT_NAME,
            repo_name=AZURE_DEVOPS_REPO_NAME,
            author_name=COMMIT_AUTHOR_NAME,
            author_email=COMMIT_AUTHOR_EMAIL,
            branch_name=TARGET_BRANCH
        )
        if success:
            print("\nCode successfully committed to Azure DevOps.")
        else:
            print("\nFailed to commit code to Azure DevOps. Check logs for details.")
    else:
        print("\nNo approved code found to commit.")

# Run the workflow
if __name__ == "__main__":
    asyncio.run(multi_agent_workflow("Write a Python function to calculate the factorial of a number"))

