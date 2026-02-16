from sqlalchemy.orm import Session

from app.services.chat_history_service import ChatHistoryService
from app.services.quality_pipeline import QualityPipeline


class PersonalPipeline:
    """
    Pipeline for personal account users
    Uses quality pipeline with web search for enhanced answers
    """
    def __init__(self, db: Session, user):
        self.db = db
        self.user = user
        self.history = ChatHistoryService(db)
        self.quality_pipeline = QualityPipeline(use_reranking=False)

    async def process(self, query: str, use_search: bool = True, max_sources: int = 20):
        """
        Process query through quality pipeline and save to chat history
        
        Args:
            query: User's question
            use_search: Whether to use web search
            max_sources: Maximum sources to include
        """
        # Get recent chat history for context
        recent = self.history.get_recent(self.user.id, limit=5)
        
        # Process query through quality pipeline
        result = await self.quality_pipeline.process_query(
            query=query,
            use_search=use_search,
            max_sources=max_sources
        )
        
        # Save to chat history
        self.history.save(
            user_id=self.user.id,
            query=query,
            answer=result["answer"],
            source="personal_with_search" if use_search else "personal_llm_only",
        )

        return result
