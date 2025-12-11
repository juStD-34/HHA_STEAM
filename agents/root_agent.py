import os
from logging import getLogger
from google.adk.agents import LlmAgent

logger = getLogger(__name__)

RootAgentName = "RootAgent"
RootOutputKey = "root_response"


def _read_root_agent_instruction() -> str:
    """
    Reads the instruction file for the root agent.

    Returns:
        The instruction content as a string, or a default instruction if file not found.
    """
    base_dir = os.path.dirname(__file__)
    instruction_path = os.path.abspath(
        os.path.join(base_dir, "..", "instructions", "root_agent.md")
    )
    try:
        with open(instruction_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.error(
            "Root agent instruction file not found",
            extra={"component": "career_counseling", "path": instruction_path},
        )
        return (
            "You are the RootAgent orchestrating a career counseling chat for high school students. "
            "Coordinate the overall conversation, conceptually using CareerAgent and QuizDeciderAgent, "
            "and always respond in warm, supportive Vietnamese."
        )
    except Exception as e:
        logger.error(
            "Failed to read root agent instruction",
            extra={"component": "career_counseling", "error": str(e)},
        )
        return (
            "You are the RootAgent orchestrating a career counseling chat for high school students. "
            "Coordinate the overall conversation, conceptually using CareerAgent and QuizDeciderAgent, "
            "and always respond in warm, supportive Vietnamese."
        )