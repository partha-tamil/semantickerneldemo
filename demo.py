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

azure_endpoint = ""
azure_deployment_name = "gpt-4"
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
researcher = ChatCompletionAgent(
    kernel=kernel,
    name="Researcher",
    instructions="You are a research assistant. Provide factual information about any topic."
)

writer = ChatCompletionAgent(
    kernel=kernel,
    name="Writer",
    instructions="You are a writer. Use the research provided to write a concise summary."
)


async def multi_agent_workflow(topic: str):
    # Step 1: Researcher gathers information
    research_chat = ChatHistory()
    research_chat.add_user_message(f"Research the topic: {topic}")
    async for research_response in researcher.invoke(research_chat):
        print("\n📚 Research Output:\n", research_response.content)


    # Step 2: Writer creates a summary
    writer_chat = ChatHistory()
    writer_chat.add_user_message(f"Based on this research, write a summary:\n{research_response.content}")
    async for writer_response in writer.invoke(writer_chat):
      print("\n✍️ Written Summary:\n", writer_response.content)


# Run the workflow
if __name__ == "__main__":
    asyncio.run(multi_agent_workflow("Benefits of renewable energy"))
