import asyncio
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.contents.chat_history import ChatHistory

from semantic_kernel.connectors.ai.open_ai import (
    AzureChatCompletion,
    OpenAIChatCompletion,
)

# Replace with your OpenAI credentials
OPENAI_API_KEY = ""

azure_endpoint = "/"
azure_deployment_name = ""
azure_api_key = ""

# Initialize the kernel and AI service
kernel = Kernel()
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
    " Give final approved code. Start with 'Approved Code' and end with 'End of approved Code'.\n\nExample:\n\nApproved Code:\n```Your code here\n```\n\nEnd of approved Code."
)


async def multi_agent_workflow(topic: str):
    # Step 1: Coder writes code
    code_chat = ChatHistory()
    code_chat.add_user_message(f"Write code for the topic: {topic}")
    async for code_response in coder.invoke(code_chat):
        print("\n� Code Output:\n", code_response.content)


    # Step 2: CodeReviewer critiques the implementation
    reviewer_chat = ChatHistory()
    reviewer_chat.add_user_message(f"Based on this code, provide a critique and suggest improvements:\n{code_response.content}")
    async for reviewer_response in codereviewer.invoke(reviewer_chat):
        print("\n📝 Code Review Feedback:\n", reviewer_response.content)


# Run the workflow
if __name__ == "__main__":
    asyncio.run(multi_agent_workflow("Write a Python function to calculate the factorial of a number"))
