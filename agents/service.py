import os
from logging import getLogger

from google.adk.agents import LlmAgent
from google.adk.tools import AgentTool

from .career_agent import build_career_agent
from .quiz_decider_agent import build_quiz_decider_agent
from .uni_search_agent import build_university_search_agent
from .root_agent import _read_root_agent_instruction

logger = getLogger(__name__)

# Cho phép override model qua env, default là gemini-2.5-flash
DEFAULT_MODEL = os.getenv("CAREER_AGENT_MODEL", "gemini-2.5-flash")


def build_agent() -> LlmAgent:
    """
    Root orchestrator for DISC-based career counseling.

    Đây là entrypoint mà lệnh `adk run career_counselor_agent` sẽ gọi.
    Orchestrator nói chuyện trực tiếp với học sinh và dùng 2 sub-agent:
    - CareerAgent: quyết định đã đủ dữ liệu để gợi ý nghề chưa
    - QuizDeciderAgent: chọn câu hỏi DISC tiếp theo nếu cần hỏi thêm
    """
    model = DEFAULT_MODEL

    # Sub-agents chuyên biệt
    career_agent = build_career_agent(model=model)
    quiz_decider_agent = build_quiz_decider_agent(model=model)
    university_search_agent = build_university_search_agent(model=model)

    # Instruction dùng chung từ file root_agent.md
    try:
        instruction = _read_root_agent_instruction()
    except Exception as e:
        logger.error(
            "Failed to read root agent instruction in orchestrator",
            extra={"component": "career_counseling", "error": str(e)},
        )
        instruction = (
            "You are the RootAgent orchestrating a DISC-based career counseling "
            "conversation for high school students. Talk directly with the user "
            "in warm, supportive Vietnamese and delegate to CareerAgent and "
            "QuizDeciderAgent tools when needed."
        )

    # Root LlmAgent đóng vai trò orchestrator + chat trực tiếp với user
    return LlmAgent(
        name="career_root_orchestrator",
        model=model,
        description=(
            "Root orchestrator for DISC-based career counseling. "
            "Talks directly with the student in Vietnamese and uses "
            "CareerAgent + QuizDeciderAgent as tools."
        ),
        instruction=instruction,
        tools=[
            AgentTool(career_agent),
            AgentTool(quiz_decider_agent),
            AgentTool(university_search_agent),
        ],
        output_key="root_response",
    )

root_agent= build_agent()