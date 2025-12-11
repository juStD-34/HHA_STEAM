from __future__ import annotations

import asyncio
from dataclasses import dataclass
from logging import getLogger
from typing import Optional

from google.adk.runners import (
    InMemorySessionService,
    RunConfig,
    Runner,
    types,
)

from .root_agent import build_agent

logger = getLogger(__name__)

DEFAULT_APP_NAME = "career_counselor_chat"


@dataclass(slots=True)
class AgentResponse:
    """Normalized response payload returned to Flask/UI callers."""

    text: str
    raw_event: Optional[object] = None


class CareerCounselorService:
    """Wraps the ADK LlmAgent so Flask routes can call it like a normal function."""

    def __init__(
        self,
        *,
        agent=None,
        app_name: str = DEFAULT_APP_NAME,
        session_service: Optional[InMemorySessionService] = None,
    ) -> None:
        self._app_name = app_name
        self._agent = agent or build_agent()
        self._session_service = session_service or InMemorySessionService()

    async def ask_async(
        self,
        message: str,
        *,
        user_id: str = "user123",
        session_id: Optional[str] = None,
    ) -> AgentResponse:
        """Send a single user message to the agent and return the final reply."""
        if not message:
            raise ValueError("message must not be empty")

        session = await self._ensure_session(user_id=user_id, session_id=session_id)
        runner = Runner(
            agent=self._agent,
            app_name=self._app_name,
            session_service=self._session_service,
        )
        user_content = types.Content(
            role="user",
            parts=[types.Part(text=message)],
        )

        final_text: Optional[str] = None
        final_event = None

        async for event in runner.run_async(
            user_id=session.user_id,
            session_id=session.id,
            new_message=user_content,
            run_config=RunConfig(streaming_mode=None),
        ):
            if event.is_final_response():
                final_text = _extract_text_from_event(event)
                final_event = event
                break

        if final_text is None:
            raise RuntimeError("Agent returned no final response")

        return AgentResponse(text=final_text, raw_event=final_event)

    def ask(
        self,
        message: str,
        *,
        user_id: str = "user123",
        session_id: Optional[str] = None,
    ) -> AgentResponse:
        """Sync helper that runs ask_async for non-async Flask routes."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.ask_async(message, user_id=user_id, session_id=session_id)
            )
        else:
            raise RuntimeError(
                "ask() cannot be called from within an active asyncio loop; "
                "use await ask_async(...) instead."
            )

    async def _ensure_session(
        self,
        *,
        user_id: str,
        session_id: Optional[str],
    ):
        session_key = session_id or f"{self._app_name}_{user_id}"
        session = await self._session_service.get_session(
            app_name=self._app_name,
            user_id=user_id,
            session_id=session_key,
        )
        if session is None:
            session = await self._session_service.create_session(
                app_name=self._app_name,
                user_id=user_id,
                session_id=session_key,
            )
        return session


def _extract_text_from_event(event) -> str:
    """Grab best-effort text output from a final ADK event."""
    try:
        parts = getattr(event, "content", None).parts  # type: ignore[attr-defined]
    except AttributeError:
        return ""

    texts = [part.text for part in parts if hasattr(part, "text")]
    return "\n".join(filter(None, texts))


# Default singleton used by the Flask app.
career_service = CareerCounselorService()
