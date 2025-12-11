import os
from logging import getLogger
from google.adk.agents import LlmAgent

logger = getLogger(__name__)

QuizDeciderAgentName = "QuizDeciderAgent"
QuizDeciderOutputKey = "quiz_decision"


def _read_quiz_decider_instruction() -> str:
    """
    Reads the instruction file for the quiz decider agent.

    Returns:
        The instruction content as a string, or a default instruction if file not found.
    """
    base_dir = os.path.dirname(__file__)
    instruction_path = os.path.abspath(
        os.path.join(base_dir, "..", "instructions", "quiz_decider.md")
    )
    try:
        with open(instruction_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.error(
            "Quiz decider instruction file not found",
            extra={"component": "career_counseling", "path": instruction_path},
        )
        return (
            "You are a psychologist deciding the next DISC-based question for a high school student. "
            "Review the chat history, find which DISC dimension (D, I, S, C) is least explored, "
            "and return exactly ONE short, natural Vietnamese question targeting that dimension."
        )
    except Exception as e:
        logger.error(
            "Failed to read quiz decider instruction",
            extra={"component": "career_counseling", "error": str(e)},
        )
        return (
            "You are a psychologist deciding the next DISC-based question for a high school student. "
            "Review the chat history, find which DISC dimension (D, I, S, C) is least explored, "
            "and return exactly ONE short, natural Vietnamese question targeting that dimension."
        )


def build_quiz_decider_agent(*, model: str) -> LlmAgent:
    """
    Builds the quiz decider agent that outputs the next DISC-based question.

    The agent will:
    - Review the conversation history and existing DISC signals.
    - Identify which DISC dimension should be explored next.
    - Output exactly ONE short, age-appropriate question in Vietnamese.
    - The response is only the question text (no explanations, no JSON).

    Args:
        model: The Gemini / Vertex model name (e.g., "gemini-2.5-flash").

    Returns:
        A configured LlmAgent that outputs a single Vietnamese question as `quiz_decision`.
    """
    return LlmAgent(
        name=QuizDeciderAgentName,
        model=model,
        description=(
            "QuizDeciderAgent: selects the next best DISC-based question for a high school student "
            "based on conversation history, and returns exactly one short question in Vietnamese."
        ),
        instruction=_read_quiz_decider_instruction(),
        tools=[],
        output_key=QuizDeciderOutputKey,
    )
