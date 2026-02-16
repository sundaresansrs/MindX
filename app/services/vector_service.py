from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List, Dict, Any
import logging

from app.models.document import Document
from app.services.embeddings import EmbeddingsService

logger = logging.getLogger(__name__)

class VectorService:
    """
    Service for semantic document retrieval using pgvector
    """
    def __init__(self, db: Session):
        self.db = db
        self.embeddings_service = EmbeddingsService()

    async def search_documents(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search for documents similar to the query string
        
        Returns:
            List of dicts with content, source_url, and distance score
        """
        try:
            # Generate embedding for the query
            query_vec = self.embeddings_service.get_embeddings([query])[0]
            
            # Perform similarity search using pgvector
            # We use cosine distance (<=>) as it's best for Jina embeddings
            stmt = select(Document).order_by(
                Document.embedding.cosine_distance(query_vec)
            ).limit(limit)
            
            results = self.db.scalars(stmt).all()
            
            # Format results for the pipeline
            formatted_results = []
            for doc in results:
                formatted_results.append({
                    "title": f"Document: {doc.source_url}" if doc.source_url else "Local Document",
                    "url": doc.source_url or "internal://document",
                    "snippet": doc.content,  # Pipeline expects snippet
                    "source": "vector_store"
                })
                
            return formatted_results
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []
