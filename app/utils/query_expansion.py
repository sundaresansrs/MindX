
from app.services.llm_service import LLMService

class QueryExpansion:
    def __init__(self):
        self.llm_service = LLMService()

    def expand(self, query: str, num_expansions: int = 3) -> list[str]:
        prompt = f"Generate {num_expansions} alternative phrasings of the following query: {query}"
        response = self.llm_service.generate_text(prompt)
        return response.strip().split('\n')
