from sqlalchemy.orm import Session

from app.services.chat_history_service import ChatHistoryService
from app.services.llm_service import LLMService


class PersonalPipeline:
    def __init__(self, db: Session, user):
        self.db = db
        self.user = user
        self.history = ChatHistoryService(db)
        self.llm = LLMService()

    async def process(self, query: str):
        recent = self.history.get_recent(self.user.id, limit=5)

        context = "\n".join(
            f"Q: {r.query}\nA: {r.answer}" for r in recent
        )

        answer = await self.llm.generate_response(
            prompt=query,
            context=context,
        )

        self.history.save(
            user_id=self.user.id,
            query=query,
            answer=answer,
            source="personal",
        )

        return {
            "answer": answer,
            "sources": [],
        }
