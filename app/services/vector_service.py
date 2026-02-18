from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List, Dict, Any, Optional
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

    async def search_documents(self, query: str, user_id: Any, session_id: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search for documents similar to the query string, filtered by user
        
        Returns:
            List of dicts with content, source_url, and distance score
        """
        try:
            # Generate embedding for the query
            query_vec = self.embeddings_service.get_embeddings([query])[0]
            
            # Perform similarity search using pgvector
            # Filter by user AND session if session_id is provided
            filters = [Document.user_id == user_id]
            if session_id:
                filters.append(Document.session_id == session_id)
            else:
                filters.append(Document.session_id == None) # Default to global/no-session
                
            # Use string representation and explicit cast to avoid operator errors
            vec_str = "[" + ",".join(map(str, query_vec)) + "]"
            from sqlalchemy import text
            
            stmt = select(Document).where(
                *filters
            ).order_by(
                text(f"embedding <=> '{vec_str}'::vector")
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
            self.db.rollback()
            return []

    async def ingest_document(self, content: str, user_id: Any, source_url: Optional[str] = None, session_id: Optional[str] = None) -> Document:
        """
        Integrate a document into the vector store: embed and save.
        """
        try:
            # Generate embedding
            embedding = self.embeddings_service.get_embeddings([content])[0]
            
            # Save to DB
            new_doc = Document(
                content=content,
                source_url=source_url,
                embedding=embedding,
                user_id=user_id,
                session_id=session_id
            )
            self.db.add(new_doc)
            self.db.commit()
            self.db.refresh(new_doc)
            return new_doc
        except Exception as e:
            logger.error(f"Ingestion failed: {e}")
            self.db.rollback()
            raise e
