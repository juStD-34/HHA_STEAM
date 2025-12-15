import os
from logging import getLogger
from google.adk.agents import LlmAgent

logger = getLogger(__name__)

ReportAgentName = "ReportAgent"
ReportOutputKey = "final_report"


def _read_report_agent_instruction() -> str:
    """
    Reads the instruction file for the report agent.

    Returns:
        The instruction content as a string, or a default instruction if file not found.
    """
    base_dir = os.path.dirname(__file__)
    instruction_path = os.path.abspath(
        os.path.join(base_dir, "..", "instructions", "report_agent.md")
    )
    try:
        with open(instruction_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.error(
            "Report agent instruction file not found",
            extra={"component": "career_counseling", "path": instruction_path},
        )
        return (
            "You generate the final Vietnamese report that combines CareerAgent recommendations "
            "with IngeousTest and ReflexTest metrics (time + mistake/quantity). "
            "Explain what each test result implies and connect them to the recommended careers."
        )
    except Exception as exc:
        logger.error(
            "Failed to read report agent instruction",
            extra={"component": "career_counseling", "error": str(exc)},
        )
        return (
            "You generate the final Vietnamese report that combines CareerAgent recommendations "
            "with IngeousTest and ReflexTest metrics (time + mistake/quantity). "
            "Explain what each test result implies and connect them to the recommended careers."
        )


def build_report_agent(*, model: str) -> LlmAgent:
    """
    Builds the report agent that merges test metrics with career guidance.

    Args:
        model: The Gemini / Vertex model name (e.g., "gemini-2.5-flash").

    Returns:
        A configured LlmAgent emitting a final Vietnamese report as `final_report`.
    """
    return LlmAgent(
        name=ReportAgentName,
        model=model,
        description=(
            "ReportAgent: combines CareerAgent output with IngeousTest/ReflexTest metrics "
            "and delivers the final Vietnamese counseling report."
        ),
        instruction=_read_report_agent_instruction(),
        tools=[],
        output_key=ReportOutputKey,
    )
