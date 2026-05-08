from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class PendingConfirmation(TypedDict):
    token: str
    tool_calls: list[dict[str, Any]]


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    summary: str
    pending_confirmation: PendingConfirmation | None
    confirmation_token: str | None
    thread_id: str
    user: dict[str, Any]
    last_tool_results: list[dict[str, Any]]
