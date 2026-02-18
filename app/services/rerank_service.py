import asyncio
import cohere
import logging
from app.config import settings

logger = logging.getLogger(__name__)

class RerankService:
    def __init__(self):
        # Initialized with timeout to prevent hangs
        self.co = cohere.AsyncClient(settings.COHERE_API_KEY, timeout=15)

    async def rerank(self, query: str, results: list[dict], top_n: int = 10) -> list[dict]:
        """
        Rerank dictionary results using Cohere.
        """
        if not results:
            return []
            
        try:
            # Extract content for reranking
            documents = [r.get("snippet") or r.get("content") or "" for r in results]
            
            # Use async rerank with 15s timeout protection
            response = await self.co.rerank(
                query=query,
                documents=documents,
                top_n=top_n,
                model="rerank-english-v3.0" # Upgrade to v3
            )
            
            # Map back to original result objects
            ranked_results = []
            for hit in response.results:
                original_idx = hit.index
                ranked_results.append(results[original_idx])
            
            return ranked_results
            
        except Exception as e:
            logger.error(f"Reranking failed: {e}")
            return results[:top_n] # Fallback to original order
