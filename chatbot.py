import os
import argparse
from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import HumanMessage

from langgraph.prebuilt import ToolNode, tools_condition

from state import ChatState
from nodes import make_chat_node
from tools import TOOLS

load_dotenv()


def detect_provider() -> str:
    """환경변수에서 사용 가능한 프로바이더를 자동 감지합니다."""
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("GOOGLE_API_KEY"):
        return "gemini"
    if os.getenv("OPENROUTER_API_KEY"):
        return "openrouter"
    raise EnvironmentError(
        "API 키가 없습니다. .env 파일에 ANTHROPIC_API_KEY, GOOGLE_API_KEY, 또는 OPENROUTER_API_KEY를 설정하세요."
    )


def build_graph(provider: str):
    """StateGraph를 조립합니다.
    chat → (툴 호출 필요 시) tools → chat → ... → END
    """
    graph = StateGraph(ChatState)
    graph.add_node("chat", make_chat_node(provider))
    graph.add_node("tools", ToolNode(TOOLS))

    graph.add_edge(START, "chat")
    # 모델이 tool_call을 반환하면 tools 노드로, 아니면 END
    graph.add_conditional_edges("chat", tools_condition)
    graph.add_edge("tools", "chat")  # 툴 실행 후 다시 chat으로

    return graph.compile()


def run(provider: str | None = None):
    provider = provider or detect_provider()
    app = build_graph(provider)
    print(f"챗봇 시작! (프로바이더: {provider}) — 종료: 'quit' 또는 Ctrl+C\n")

    history = []
    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n종료합니다.")
            break

        if user_input.lower() in ("quit", "exit", "q"):
            print("종료합니다.")
            break
        if not user_input:
            continue

        history.append(HumanMessage(content=user_input))
        result = app.invoke({"messages": history})

        ai_msg = result["messages"][-1]
        print(f"AI: {ai_msg.content}\n")

        history = result["messages"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--provider", choices=["anthropic", "gemini", "openrouter"],
        help="사용할 LLM 프로바이더 (기본: 환경변수에서 자동 감지)"
    )
    args = parser.parse_args()
    run(provider=args.provider)
