
from app.services.embedding_service import EmbeddingService
from app.services.vector_service import VectorService

class DocumentService:
    def __init__(self):
        self.embedding_service = EmbeddingService()
        self.vector_service = VectorService()

    def add_document(self, doc_id: str, content: str):
        embedding = self.embedding_service.generate_embeddings([content])[0]
        self.vector_service.add_vector(doc_id, embedding)
