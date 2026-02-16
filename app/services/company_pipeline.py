from sqlalchemy.orm import Session

from app.services.chat_history_service import ChatHistoryService
from app.services.quality_pipeline import QualityPipeline


class CompanyPipeline:
    """
    Pipeline for company account users
    Currently uses quality pipeline with web search
    Future: Will add Hybrid RAG (web + internal documents)
    """
    def __init__(self, db: Session, user):
        self.db = db
        self.user = user
        self.history = ChatHistoryService(db)
        # Enable re-ranking for company accounts (premium feature)
        self.quality_pipeline = QualityPipeline(db=db, use_reranking=True)


    async def process(self, query: str, use_search: bool = True, max_sources: int = 20):
        """
        Process query through quality pipeline with optional company documents
        
        Args:
            query: User's question
            use_search: Whether to use web search
            max_sources: Maximum sources to include
            
        Note: Hybrid RAG (company documents) will be added in future step
        """
        # Get recent chat history for context
        recent = self.history.get_recent(self.user.id, limit=5)
        
        # Process query through quality pipeline
        # Future: Add company document retrieval here
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
            source="company_with_search" if use_search else "company_llm_only",
        )

        return result
