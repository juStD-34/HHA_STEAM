import os
from logging import getLogger
from google.adk.agents import LlmAgent

logger = getLogger(__name__)

CareerAgentName = "CareerAgent"
CareerOutputKey = "career_decision"


def _read_career_agent_instruction() -> str:
    """
    Reads the instruction file for the career agent.

    Returns:
        The instruction content as a string, or a default instruction if file not found.
    """
    base_dir = os.path.dirname(__file__)
    instruction_path = os.path.abspath(
        os.path.join(base_dir,  "instructions", "career_agent.md")
    )
    try:
        with open(instruction_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.error(
            "Career agent instruction file not found",
            extra={"component": "career_counseling", "path": instruction_path},
        )
        return (
            "You are a professional career counselor for high school students. "
            "Review the conversation history, decide whether you already have enough information "
            "to recommend 3–5 suitable career domains, or if you need more information. "
            "If more info is needed, explain gently (in Vietnamese) that you will ask another question. "
            "Always respond in warm, supportive Vietnamese."
        )
    except Exception as e:
        logger.error(
            "Failed to read career agent instruction",
            extra={"component": "career_counseling", "error": str(e)},
        )
        return (
            "You are a professional career counselor for high school students. "
            "Review the conversation history, decide whether you already have enough information "
            "to recommend 3–5 suitable career domains, or if you need more information. "
            "If more info is needed, explain gently (in Vietnamese) that you will ask another question. "
            "Always respond in warm, supportive Vietnamese."
        )


def build_career_agent(*, model: str) -> LlmAgent:
    """
    Builds the career agent that analyzes the student's profile and decides next steps.

    The agent will:
    - Review chat history and DISC / interests / skills signals.
    - Decide whether information is sufficient to recommend broad career domains.
    - Either:
      - Provide 3–5 recommended job domains with explanations; or
      - Explain that more information is needed and that another question will follow.
    - Always respond in Vietnamese in a happy, peaceful tone.

    Args:
        model: The Gemini / Vertex model name (e.g., "gemini-2.5-flash").

    Returns:
        A configured LlmAgent that outputs a natural-language `career_decision`.
    """
    return LlmAgent(
        name=CareerAgentName,
        model=model,
        description=(
            "CareerAgent for high school students: reviews chat history and DISC signals, "
            "decides whether to recommend career domains or gather more information. "
            "Outputs a Vietnamese natural-language decision and recommendations."
        ),
        instruction=_read_career_agent_instruction(),
        tools=[],
        output_key=CareerOutputKey,
    )
