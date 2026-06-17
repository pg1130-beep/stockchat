from typing import Annotated
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class ChatState(TypedDict):
    """챗봇의 상태. 새 필드를 추가해 기능을 확장하세요."""
    messages: Annotated[list, add_messages]
    # 확장 예시:
    # user_id: str
    # context: dict
    # tool_results: list
