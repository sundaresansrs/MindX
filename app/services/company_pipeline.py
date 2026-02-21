import asyncio
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.services.chat_history_service import ChatHistoryService
from app.services.quality_pipeline import QualityPipeline


class CompanyPipeline:
    """
    Pipeline for company account users.
    Uses quality pipeline with web search + company document RAG.
    """
    def __init__(self, db: Session, user):
        self.db = db
        self.user = user
        self.history = ChatHistoryService(db)
        # Enable re-ranking for company accounts (premium feature)
        self.quality_pipeline = QualityPipeline(db=db, use_reranking=True)

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
        session_id: Optional[str] = None,
        use_search: bool = True,
        max_sources: int = 20,
        fast_mode: bool = False,
        file_ids: Optional[list[str]] = None,
    ):
        """Process query through quality pipeline with optional company documents."""
        is_first = self.history.is_first_message(self.user.id, session_id) if session_id else False

        history_records = []
        if session_id:
            history_records = self.history.get_by_session(self.user.id, session_id)
        history_context = []
        for r in history_records:
            history_context.append({"role": "user", "content": r.query})
            history_context.append({"role": "assistant", "content": r.answer})


        result = await self.quality_pipeline.process_query(
            query=query,
            user=self.user,
            session_id=session_id,
            history=history_context,
            use_search=use_search,
            max_sources=max_sources,
            fast_mode=fast_mode,
            file_ids=file_ids,
        )

        self.history.save(
            user_id=self.user.id,
            query=query,
            answer=result["answer"],
            source=str(result["metadata"].get("sources_used", 0)),
            session_id=session_id,
            confidence=int(result.get("confidence", 0) * 100) if isinstance(result.get("confidence"), float) else result.get("confidence")
        )

        if is_first and session_id:
            asyncio.create_task(self._generate_title(session_id, query))

        return result

    # ─── Streaming search ─────────────────────────────────────────────────────

    async def stream(
        self,
        query: str,
        session_id: Optional[str] = None,
        use_search: bool = True,
        max_sources: int = 15,
        fast_mode: bool = False,
        file_ids: Optional[list[str]] = None,
    ):
        """Stream search results and save history incrementally."""
        is_first = self.history.is_first_message(self.user.id, session_id) if session_id else False

        history_records = []
        if session_id:
            history_records = self.history.get_by_session(self.user.id, session_id)
        history_context = []
        for r in history_records:
            history_context.append({"role": "user", "content": r.query})
            history_context.append({"role": "assistant", "content": r.answer})


        # LAYER 2 PERSISTENCE: Save record immediately so it exists in history if user refreshes mid-stream
        placeholder_answer = "..." 
        record = self.history.save(
            user_id=self.user.id,
            query=query,
            answer=placeholder_answer,
            source="0",
            session_id=session_id,
        )

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
            file_ids=file_ids,
        ):
            if chunk["type"] == "token":
                full_answer += chunk["content"]
            elif chunk["type"] == "metadata":
                metadata = chunk
            yield chunk

        # Update record with final response
        if full_answer:
            confidence_val = metadata.get("confidence", 0.7)
            final_confidence: Optional[int] = None
            
            if isinstance(confidence_val, float):
                final_confidence = int(confidence_val * 100)
            elif isinstance(confidence_val, (int, str)):
                try:
                    final_confidence = int(confidence_val)
                except (ValueError, TypeError):
                    pass
            
            sources_list = metadata.get("sources", [])
            sources_count = len(sources_list) if isinstance(sources_list, list) else 0

            self.history.update_answer(
                record_id=record.id,  # type: ignore
                answer=full_answer,
                source=str(sources_count),
                confidence=final_confidence
            )
            if is_first and session_id:
                asyncio.create_task(self._generate_title(session_id, query))
