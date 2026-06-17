import os
from langchain_core.language_models import BaseChatModel
from state import ChatState
from tools import TOOLS


def get_model(provider: str) -> BaseChatModel:
    """provider에 따라 LLM을 반환합니다. 새 프로바이더는 여기에 추가하세요."""
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model="claude-opus-4-8")
    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model="gemini-2.0-flash-lite")
    elif provider == "openrouter":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model="openai/gpt-oss-120b:free",
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY"),
        )
    else:
        raise ValueError(f"지원하지 않는 프로바이더: {provider!r}.")


def make_chat_node(provider: str):
    model = get_model(provider).bind_tools(TOOLS)

    def chat_node(state: ChatState) -> dict:
        response = model.invoke(state["messages"])
        return {"messages": [response]}

    return chat_node
