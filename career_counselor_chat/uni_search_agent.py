import os
from logging import getLogger
from google.adk.agents import LlmAgent

logger = getLogger(__name__)

UniversitySearchAgentName = "UniversitySearchAgent"
UniversitySearchOutputKey = "university_suggestions"


def _read_university_search_instruction() -> str:
    base_dir = os.path.dirname(__file__)
    instruction_path = os.path.abspath(
        os.path.join(base_dir, "instructions", "uni_search_agent.md") 
    )
    try:
        with open(instruction_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(
            "University search agent instruction file not found or failed to read",
            extra={"component": "career_counseling", "error": str(e)},
        )
        # fallback instruction ngắn gọn
        return (
            "Bạn là chuyên gia tư vấn tuyển sinh tại Việt Nam. "
            "Dựa trên các ngành học và từ khóa được cung cấp, "
            "hãy gợi ý một số trường đại học/cao đẳng tại Việt Nam "
            "có đào tạo các ngành đó, kèm theo tên ngành và link website tuyển sinh. "
            "Trả lời bằng tiếng Việt, văn phong gần gũi cho học sinh cấp 3."
        )


def build_university_search_agent(*, model: str) -> LlmAgent:
    return LlmAgent(
        name=UniversitySearchAgentName,
        model=model,
        description=(
            "UniversitySearchAgent: dựa trên ngành học và từ khóa, "
            "gợi ý trường đại học ở Việt Nam và link website tuyển sinh."
        ),
        instruction=_read_university_search_instruction(),
        tools=[
            # TODO: thêm search tool của bạn vào đây nếu có, ví dụ:
            # WebSearchTool(...),
        ],
        output_key=UniversitySearchOutputKey,
    )
