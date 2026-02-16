from app.services.llm_service import LLMService


class QualityPipeline:
    def __init__(self):
        self.llm_service = LLMService()

    async def process_query(self, query: str):
        answer = await self.llm_service.generate_response(query)

        return {
            "answer": answer,
            "sources": []
        }
