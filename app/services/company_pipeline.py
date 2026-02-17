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


    async def search(self, query: str, session_id: str = None, use_search: bool = True, max_sources: int = 20, fast_mode: bool = False):
        """
        Process query through quality pipeline with optional company documents
        """
        # Fetch history for context
        history_records = []
        if session_id:
            history_records = self.history.get_by_session(self.user.id, session_id)
        
        history_context = [{"query": r.query, "answer": r.answer} for r in history_records]

        # Process query through quality pipeline
        # Future: Add company document retrieval here
        result = await self.quality_pipeline.process_query(
            query=query,
            user=self.user,
            session_id=session_id,
            history=history_context,
            use_search=use_search,
            max_sources=max_sources,
            fast_mode=fast_mode
        )

        
        # Save to chat history
        self.history.save(
            user_id=self.user.id,
            query=query,
            answer=result["answer"],
            source=str(result["metadata"].get("sources_used", 0)),
            session_id=session_id
        )

        return result

    async def stream(self, query: str, session_id: str = None, use_search: bool = True, max_sources: int = 15, fast_mode: bool = False):
        """
        Stream search results and save history at the end
        """
        # Fetch history for context
        history_records = []
        if session_id:
            history_records = self.history.get_by_session(self.user.id, session_id)
        
        history_context = [{"query": r.query, "answer": r.answer} for r in history_records]
        
        full_answer = ""
        metadata = {}

        async for chunk in self.quality_pipeline.stream_query(
            query=query,
            user=self.user,
            session_id=session_id,
            history=history_context,
            use_search=use_search,
            max_sources=max_sources,
            fast_mode=fast_mode
        ):
            if chunk["type"] == "token":
                full_answer += chunk["content"]
            elif chunk["type"] == "metadata":
                metadata = chunk
            
            yield chunk

        # Save to history once stream finishes
        if full_answer:
            self.history.save(
                user_id=self.user.id,
                query=query,
                answer=full_answer,
                source=str(len(metadata.get("sources", []))),
                session_id=session_id
            )

