import asyncio
from sqlalchemy.orm import Session

from app.services.chat_history_service import ChatHistoryService
from app.services.quality_pipeline import QualityPipeline


class PersonalPipeline:
    """
    Pipeline for personal account users.
    Uses quality pipeline with web search for enhanced answers.
    """
    def __init__(self, db: Session, user):
        self.db = db
        self.user = user
        self.history = ChatHistoryService(db)
        self.quality_pipeline = QualityPipeline(db=db, use_reranking=False)

    # ─── Auto-title generation ────────────────────────────────────────────────

    async def _generate_title(self, session_id: str, first_message: str):
        """Fire a quick LLM call to auto-generate a chat title (background task)."""
        try:
            from app.services.llm_service import LLMService
            llm = LLMService()
            prompt = (
                f"Summarize this question in 5 words or fewer. "
                f"Return ONLY the title, no punctuation, no quotes:\n\n{first_message}"
            )
            title = await asyncio.wait_for(llm.generate_response(prompt), timeout=8.0)
            title = title.strip().strip('"').strip("'")[:80]
            if title:
                self.history.update_title(
                    user_id=self.user.id,
                    session_id=session_id,
                    title=title,
                )
        except Exception:
            pass  # Title generation is best-effort; never block the main flow

    # ─── Non-streaming search ─────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        session_id: str = None,
        use_search: bool = True,
        max_sources: int = 20,
        fast_mode: bool = False,
    ):
        """Process query through quality pipeline and save to chat history."""
        is_first = self.history.is_first_message(self.user.id, session_id) if session_id else False

        history_records = []
        if session_id:
            history_records = self.history.get_by_session(self.user.id, session_id)
        history_context = [{"query": r.query, "answer": r.answer} for r in history_records]

        result = await self.quality_pipeline.process_query(
            query=query,
            user=self.user,
            session_id=session_id,
            history=history_context,
            use_search=use_search,
            max_sources=max_sources,
            fast_mode=fast_mode,
        )

        self.history.save(
            user_id=self.user.id,
            query=query,
            answer=result["answer"],
            source=str(result["metadata"].get("sources_used", 0)),
            session_id=session_id,
        )

        # Auto-title: fire in background after first message
        if is_first and session_id:
            asyncio.create_task(self._generate_title(session_id, query))

        return result

    # ─── Streaming search ─────────────────────────────────────────────────────

    async def stream(
        self,
        query: str,
        session_id: str = None,
        use_search: bool = True,
        max_sources: int = 15,
        fast_mode: bool = False,
    ):
        """Stream search results and save history at the end."""
        is_first = self.history.is_first_message(self.user.id, session_id) if session_id else False

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
            fast_mode=fast_mode,
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
                session_id=session_id,
            )
            # Auto-title: fire in background after first message
            if is_first and session_id:
                asyncio.create_task(self._generate_title(session_id, query))
