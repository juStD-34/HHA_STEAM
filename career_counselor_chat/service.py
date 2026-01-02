from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import unicodedata
import os
from logging import getLogger
from typing import Optional, Dict, Any

from google.adk.runners import (
    InMemorySessionService,
    RunConfig,
    Runner,
    types,
)

from .root_agent import build_agent, DEFAULT_MODEL
from .career_agent import build_career_agent
from .report_agent import build_report_agent
from .uni_search_agent import build_university_search_agent
from vertexai import init as vertexai_init

logger = getLogger(__name__)

DEFAULT_APP_NAME = "agents"


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
        career_agent=None,
        report_agent=None,
        university_agent=None,
        app_name: str = DEFAULT_APP_NAME,
        session_service: Optional[InMemorySessionService] = None,
    ) -> None:
        self._app_name = app_name
        self._agent = agent or build_agent()
        self._career_agent = career_agent or build_career_agent(model=DEFAULT_MODEL)
        self._report_agent = report_agent or build_report_agent(model=DEFAULT_MODEL)
        self._university_agent = (
            university_agent or build_university_search_agent(model=DEFAULT_MODEL)
        )
        self._session_service = session_service or InMemorySessionService()
        self._test_metrics: Dict[str, Dict[str, Optional[Dict[str, Any]]]] = {}
        self._ensure_vertex_ai()

    def _ensure_vertex_ai(self) -> None:
        """Initialize Vertex AI if GOOGLE_CLOUD_* env vars are provided."""
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("GOOGLE_CLOUD_LOCATION")
        if not project or not location:
            logger.warning(
                "Skipping Vertex AI init because GOOGLE_CLOUD_PROJECT/LOCATION missing",
                extra={"component": "career_counseling"},
            )
            return
        try:
            vertexai_init(project=project, location=location)
            logger.info(
                "Initialized Vertex AI context",
                extra={
                    "component": "career_counseling",
                    "project": project,
                    "location": location,
                },
            )
        except Exception as exc:  # pragma: no cover - env specific
            logger.error(
                "Vertex AI init failed",
                extra={
                    "component": "career_counseling",
                    "project": project,
                    "location": location,
                    "error": str(exc),
                },
            )

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
        context_text = self._build_test_context(user_id)
        parts = []
        if context_text:
            parts.append(types.Part(text=context_text))
        parts.append(types.Part(text=message))
        user_content = types.Content(role="user", parts=parts)

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

    def generate_final_report(
        self,
        *,
        student_profile: Dict[str, Any],
        chat_history: list[dict[str, str]],
        user_id: str = "user123",
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Sync wrapper to create the JSON final report via ReportAgent."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.generate_final_report_async(
                    student_profile=student_profile,
                    chat_history=chat_history,
                    user_id=user_id,
                    session_id=session_id,
                )
            )
        else:
            raise RuntimeError(
                "generate_final_report() cannot run inside an active loop; "
                "call generate_final_report_async instead."
            )

    def generate_career_summary(
        self,
        *,
        student_profile: Dict[str, Any],
        chat_history: list[dict[str, str]],
        user_id: str = "user123",
        session_id: Optional[str] = None,
    ) -> str:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self._generate_career_summary_async(
                    student_profile=student_profile,
                    chat_history=chat_history,
                    user_id=user_id,
                    session_id=session_id,
                )
            )
        else:
            raise RuntimeError(
                "generate_career_summary() cannot run inside an active loop; "
                "use await _generate_career_summary_async(...) instead."
            )

    async def generate_final_report_async(
        self,
        *,
        student_profile: Dict[str, Any],
        chat_history: list[dict[str, str]],
        user_id: str = "user123",
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not student_profile:
            raise ValueError("Missing student profile for final report.")
        logger.info(
            "Generating final report via RootAgent",
            extra={"component": "career_counseling", "user_id": user_id},
        )
        career_summary = await self._generate_career_summary_async(
            student_profile=student_profile,
            chat_history=chat_history,
            user_id=user_id,
        )
        prompt = self._build_root_report_prompt(
            student_profile=student_profile,
            career_summary=career_summary,
            user_id=user_id,
        )
        final_text = await self._run_root_task_async(
            prompt=prompt,
            user_id=user_id,
            session_id=session_id or f"{self._app_name}_{user_id}_report_root",
        )
        if not final_text:
            raise RuntimeError("Root agent returned no output for report.")
        return self._parse_report_response(final_text)

    async def generate_university_recommendations_async(
        self,
        *,
        career_summary: str,
        student_profile: Optional[Dict[str, Any]] = None,
        user_id: str = "user123",
        session_id: Optional[str] = None,
    ) -> str:
        if not career_summary:
            raise ValueError("Missing career summary for university search.")
        logger.info(
            "Generating university suggestions via RootAgent",
            extra={"component": "career_counseling", "user_id": user_id},
        )
        prompt = self._build_root_university_prompt(
            career_summary=career_summary,
            student_profile=student_profile or {},
        )
        final_text = await self._run_root_task_async(
            prompt=prompt,
            user_id=user_id,
            session_id=session_id or f"{self._app_name}_{user_id}_university_root",
        )
        if not final_text:
            raise RuntimeError("Root agent returned no output for university.")
        return final_text.strip()

    def generate_university_recommendations(
        self,
        *,
        career_summary: str,
        student_profile: Optional[Dict[str, Any]] = None,
        user_id: str = "user123",
        session_id: Optional[str] = None,
    ) -> str:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.generate_university_recommendations_async(
                    career_summary=career_summary,
                    student_profile=student_profile,
                    user_id=user_id,
                    session_id=session_id,
                )
            )
        else:
            raise RuntimeError(
                "generate_university_recommendations() cannot run inside an active loop; "
                "use await generate_university_recommendations_async(...) instead."
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

    def update_test_metrics(
        self,
        *,
        user_id: str,
        ingenuous: Optional[Dict[str, Any]] = None,
        reflex: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Store the latest Ingeous/Reflex test metrics for downstream prompts."""
        payload = self._test_metrics.setdefault(
            user_id, {"ingenuous": None, "reflex": None}
        )
        if ingenuous:
            payload["ingenuous"] = {
                "time": float(ingenuous.get("time", 0.0) or 0.0),
                "mistake": int(ingenuous.get("mistake", 0) or 0),
            }
        if reflex:
            payload["reflex"] = {
                "time": float(reflex.get("time", 0.0) or 0.0),
                "quantity": int(reflex.get("quantity", 0) or 0),
            }

    def reset_test_metrics(self, *, user_id: str) -> None:
        """Clear cached test metrics for a user after a session finishes."""
        self._test_metrics.pop(user_id, None)

    def _build_root_report_prompt(
        self,
        *,
        student_profile: Dict[str, Any],
        career_summary: str,
        user_id: str,
    ) -> str:
        profile_line = (
            f"Học sinh: name={student_profile.get('full_name', '')}, "
            f"age={student_profile.get('age', '')}, "
            f"class={student_profile.get('class_name', '')}, "
            f"grade={student_profile.get('grade', '')}, "
            f"gender={student_profile.get('gender', '')}"
        )
        lines = [
            "TASK: REPORT",
            "Su dung agent de tao report cho ket qua chat ben tren ket hop voi ket qua lam bai test 1 va bai test 2.",
            profile_line,
            "CareerAgentOutput:",
            career_summary,
        ]
        test_context = self._build_test_context(user_id)
        if test_context:
            lines.append(test_context)
        lines.append(
            "Yeu cau: goi ReportAgent va tra ve JSON voi keys name, age, class, fit_job, explanation."
        )
        return "\n".join(filter(None, lines))

    async def _generate_career_summary_async(
        self,
        *,
        student_profile: Dict[str, Any],
        chat_history: list[dict[str, str]],
        user_id: str,
        session_id: Optional[str] = None,
    ) -> str:
        if not chat_history:
            raise ValueError("Missing chat history for career summary.")
        prompt = self._build_career_prompt(
            student_profile=student_profile,
            chat_history=chat_history,
        )
        career_session_id = session_id or f"{self._app_name}_{user_id}_career"
        session = await self._ensure_session(
            user_id=user_id,
            session_id=career_session_id,
        )
        runner = Runner(
            agent=self._career_agent,
            app_name=self._app_name,
            session_service=self._session_service,
        )
        user_content = types.Content(role="user", parts=[types.Part(text=prompt)])
        final_text: Optional[str] = None
        async for event in runner.run_async(
            user_id=session.user_id,
            session_id=session.id,
            new_message=user_content,
            run_config=RunConfig(streaming_mode=None),
        ):
            if event.is_final_response():
                final_text = _extract_text_from_event(event)
                break
        if not final_text:
            raise RuntimeError("Career agent returned no output.")
        return final_text.strip()

    def _build_career_prompt(
        self,
        *,
        student_profile: Dict[str, Any],
        chat_history: list[dict[str, str]],
    ) -> str:
        profile_line = (
            f"Học sinh: {student_profile.get('full_name', '')} | "
            f"Giới tính: {student_profile.get('gender', '')} | "
            f"Khối: {student_profile.get('grade', '')} | "
            f"Lớp: {student_profile.get('class_name', '')} | "
            f"Tuổi: {student_profile.get('age', '')}"
        )
        lines = [profile_line, "Lịch sử hội thoại:"]
        for entry in chat_history:
            role = entry.get("role", "").strip() or "unknown"
            text = entry.get("text", "").strip()
            if not text:
                continue
            lines.append(f"{role}: {text}")
        return "\n".join(lines)

    def _build_root_university_prompt(
        self,
        *,
        career_summary: str,
        student_profile: Dict[str, Any],
    ) -> str:
        majors = self._extract_majors_from_summary(career_summary)
        majors_text = ", ".join(majors) if majors else "chưa rõ"
        profile_line = (
            f"Student profile: grade={student_profile.get('grade', '')}, "
            f"class={student_profile.get('class_name', '')}"
        )
        return "\n".join(
            [
                "TASK: UNIVERSITY",
                "Su dung agent de tim truong dai hoc phu hop dua tren tong hop nghe nghiep ben duoi.",
                profile_line,
                f"Majors inferred: {majors_text}",
                "Career summary:",
                career_summary,
            ]
        )

    async def _run_root_task_async(
        self,
        *,
        prompt: str,
        user_id: str,
        session_id: str,
    ) -> str:
        task_line = prompt.splitlines()[0] if prompt else "TASK: UNKNOWN"
        logger.info(
            "RootAgent task dispatch: %s",
            task_line,
            extra={"component": "career_counseling", "user_id": user_id},
        )
        session = await self._ensure_session(
            user_id=user_id,
            session_id=session_id,
        )
        runner = Runner(
            agent=self._agent,
            app_name=self._app_name,
            session_service=self._session_service,
        )
        user_content = types.Content(role="user", parts=[types.Part(text=prompt)])
        final_text: Optional[str] = None
        async for event in runner.run_async(
            user_id=session.user_id,
            session_id=session.id,
            new_message=user_content,
            run_config=RunConfig(streaming_mode=None),
        ):
            if event.is_final_response():
                final_text = _extract_text_from_event(event)
                break
        return final_text or ""

    def _extract_majors_from_summary(self, summary: str) -> list[str]:
        majors: list[str] = []
        lines = [line.strip() for line in summary.splitlines() if line.strip()]
        capture = False
        for line in lines:
            lowered = line.lower()
            if "ngành học" in lowered or "nganh hoc" in lowered:
                capture = True
                continue
            if capture and (line.startswith("**") or line.endswith(":")):
                break
            if capture and line.startswith(("-", "*")):
                item = line.lstrip("-* ").strip()
                if item:
                    majors.append(item)
            elif capture and not line.startswith(("-", "*")):
                break
        return majors

    def is_characteristic_ready(self, text: str) -> bool:
        if not text:
            return False
        lowered = text.lower()
        markers = (
            "điểm nổi bật tính cách",
            "diem noi bat tinh cach",
            "điểm mạnh nổi bật",
            "diem manh noi bat",
        )
        return any(marker in lowered for marker in markers)

    def is_chat_done(self, text: str) -> bool:
        if not text:
            return False
        lowered = text.lower()
        normalized = unicodedata.normalize("NFKD", lowered)
        stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        return "ket luan cuoi" in stripped

    def _parse_report_response(self, text: str) -> Dict[str, Any]:
        normalized = text.strip()
        if normalized.startswith("```"):
            # Strip common Markdown code fences (```json ... ```)
            normalized = normalized.lstrip("`")
            fence_end = normalized.find("\n")
            if fence_end != -1:
                normalized = normalized[fence_end + 1 :]
            closing = normalized.rfind("```")
            if closing != -1:
                normalized = normalized[:closing]
        try:
            data = json.loads(normalized)
        except json.JSONDecodeError as exc:  # pragma: no cover - depends on agent output
            raise ValueError("Report agent returned invalid JSON.") from exc

        for key in ("name", "age", "class", "fit_job", "explanation"):
            data.setdefault(key, "")
        return data

    def _build_test_context(self, user_id: str) -> Optional[str]:
        metrics = self._test_metrics.get(user_id)
        if not metrics:
            return None
        lines = []
        ingenuous = metrics.get("ingenuous")
        reflex = metrics.get("reflex")
        if ingenuous:
            lines.append(
                "IngeousTest: "
                f"time={ingenuous['time']:.2f}s, mistake={ingenuous['mistake']}"
            )
        if reflex:
            lines.append(
                "ReflexTest: "
                f"time={reflex['time']:.2f}s, quantity={reflex['quantity']}"
            )
        if not lines:
            return None
        return (
            "SYSTEM CONTEXT (test metrics for ReportAgent):\n" + "\n".join(lines)
        )


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
