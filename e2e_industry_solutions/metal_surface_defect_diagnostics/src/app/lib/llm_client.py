"""Client for the Foundation Model API chat endpoint."""

from __future__ import annotations

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import ChatMessage, ChatMessageRole


def generate_report(
    w: WorkspaceClient,
    endpoint: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.1,
    max_tokens: int = 900,
) -> str:
    """Return the model's text answer. Raises on transport errors or an empty answer."""
    response = w.serving_endpoints.query(
        name=endpoint,
        messages=[
            ChatMessage(role=ChatMessageRole.SYSTEM, content=system_prompt),
            ChatMessage(role=ChatMessageRole.USER, content=user_prompt),
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    choices = response.choices or []
    content = choices[0].message.content if choices and choices[0].message else None
    if not content or not content.strip():
        raise ValueError("The LLM returned an empty answer")
    return content.strip()
