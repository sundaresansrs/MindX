
import cohere
from app.config import settings

class RerankService:
    def __init__(self):
        self.co = cohere.Client(settings.COHERE_API_KEY)

    def rerank(self, query: str, documents: list[str], top_n: int = 5) -> list[dict]:
        response = self.co.rerank(
            query=query,
            documents=documents,
            top_n=top_n,
            model="rerank-english-v2.0"
        )
        return [result.document for result in response.results]
