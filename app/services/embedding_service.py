
import cohere
from app.config import settings

class EmbeddingService:
    def __init__(self):
        self.co = cohere.Client(settings.COHERE_API_KEY)

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        response = self.co.embed(
            texts=texts,
            model="embed-english-v3.0",
            input_type="search_document"
        )
        return response.embeddings
