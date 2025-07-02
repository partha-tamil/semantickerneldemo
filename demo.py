import asyncio
import os
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import (
    AzureChatCompletion,
    OpenAIChatCompletion,
)
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.contents.chat_history import ChatHistory

async def main():
    # 1. Initialize the Kernel
    kernel = Kernel()

    # 2. Configure an AI Service (e.g., OpenAI or Azure OpenAI)
    # Choose one of the following based on your setup:

    # Option A: OpenAI
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        kernel.add_service(
            OpenAIChatCompletion(service_id="default", ai_model_id="gpt-3.5-turbo")
        )
        print("Using OpenAI GPT-3.5-turbo")
    else:
        # Option B: Azure OpenAI
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

    # 3. Define the Agent
    # A simple agent with basic instructions
    agent = ChatCompletionAgent(
        service_id="default",  # Use the service configured above
        kernel=kernel,
        name="SK-Assistant",
        instructions="You are a helpful and friendly assistant. You respond concisely.",
    )

    # 4. Create a Chat History
    chat_history = ChatHistory()

    print("\nSK-Assistant Demo (type 'exit' to quit)\n")
    while True:
        user_input = input("User > ")
        if user_input.lower() == "exit":
            break

        # Add user message to history
        chat_history.add_user_message(user_input)

        # 5. Invoke the Agent
        # The agent processes the conversation history and generates a response
        response = await agent.invoke(chat_history)

        # 6. Print the Agent's Response
        print(f"Assistant > {response.content}")

        # Add agent's response to history for context in next turn
        chat_history.add_assistant_message(response.content)

if __name__ == "__main__":
    # Ensure you set your environment variables before running, e.g.:
    # export OPENAI_API_KEY="YOUR_OPENAI_API_KEY"
    # or
    # export AZURE_OPENAI_ENDPOINT="YOUR_AZURE_OPENAI_ENDPOINT"
    # export AZURE_OPENAI_DEPLOYMENT_NAME="YOUR_AZURE_OPENAI_DEPLOYMENT_NAME"
    # export AZURE_OPENAI_API_KEY="YOUR_AZURE_OPENAI_API_KEY"
    asyncio.run(main())
