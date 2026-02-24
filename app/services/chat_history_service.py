import uuid
import asyncio
from typing import Optional, Any, List, Dict
from sqlalchemy.orm import Session  # type: ignore
from sqlalchemy import func, desc
from app.models.chat_history import ChatHistory  # type: ignore


class ChatHistoryService:
    def __init__(self, db: Session):
        self.db = db

    # ─── Save a message ──────────────────────────────────────────────────────

    def save(
        self,
        user_id: int,
        query: str,
        answer: str,
        source: str,
        session_id: Optional[str] = None,
        title: Optional[str] = None,
        confidence: Optional[int] = None,
    ):
        sid: Any = session_id
        if session_id and isinstance(session_id, str):
            try:
                sid = uuid.UUID(session_id)
            except ValueError:
                sid = None

        # Ensuring the conversation exists and belongs to the user
        if sid:
            from app.models.conversation import Conversation
            existing_conv = self.db.query(Conversation).filter(Conversation.id == sid).first()
            
            if existing_conv:
                if existing_conv.user_id != user_id:
                    # Security breach attempt or UUID collision
                    raise ValueError("Target conversation belongs to another user")
            else:
                # Create new conversation for this user
                conv = Conversation(
                    id=sid,
                    user_id=user_id,
                    title=title or (query[:100] + ("..." if len(query) > 100 else ""))
                )
                self.db.add(conv)
                self.db.commit()
        
        # Count existing messages for the session
        existing_count = 0
        latest_version = 0
        if sid:
            existing_count = (
                self.db.query(func.count(ChatHistory.id))
                .filter(ChatHistory.user_id == user_id, ChatHistory.conversation_id == sid)
                .scalar()
                or 0
            )
            latest_version = (
                self.db.query(func.max(ChatHistory.version))
                .filter(ChatHistory.user_id == user_id, ChatHistory.conversation_id == sid, ChatHistory.query == query)
                .scalar()
                or 0
            )

        record = ChatHistory(
            user_id=user_id,
            query=query,
            answer=answer,
            source=source,
            session_id=sid,
            conversation_id=sid,
            title=title,
            preview=query[:100] + ("..." if len(query) > 100 else ""),
            message_count=existing_count + 1,
            version=latest_version + 1,
            confidence=confidence
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    # ─── Update title for all rows in a session ───────────────────────────────

    def update_title(self, user_id: int, session_id: str, title: str):
        sid: Any = session_id
        try:
            sid = uuid.UUID(session_id)
        except ValueError:
            return

        # Update Conversation table
        from app.models.conversation import Conversation
        self.db.query(Conversation).filter(
            Conversation.id == sid,
            Conversation.user_id == user_id
        ).update({"title": title})

        # Update all messages in that session
        self.db.query(ChatHistory).filter(
            ChatHistory.user_id == user_id,
            ChatHistory.conversation_id == sid,
        ).update({"title": title})
        self.db.commit()

    # ─── Get session list (one entry per session, most recent first) ──────────

    def get_sessions_list(self, user_id: int, limit: int = 100) -> List[Dict]:
        """
        Returns one row per session using the dedicated Conversations table.
        Strictly filtered by user_id for isolation.
        """
        from app.models.conversation import Conversation
        
        # Join Conversation with its most recent message
        sessions = (
            self.db.query(Conversation)
            .filter(Conversation.user_id == user_id)
            .order_by(desc(Conversation.updated_at))
            .limit(limit)
            .all()
        )

        result = []
        for conv in sessions:
            # Get latest message for preview
            latest_msg = (
                self.db.query(ChatHistory)
                .filter(ChatHistory.conversation_id == conv.id)
                .order_by(desc(ChatHistory.created_at))
                .first()
            )
            
            if not latest_msg:
                continue

            # Get total message count
            count = (
                self.db.query(func.count(ChatHistory.id))
                .filter(ChatHistory.conversation_id == conv.id)
                .scalar()
                or 0
            )
            
            result.append({
                "session_id": str(conv.id),
                "title": conv.title or (str(latest_msg.query)[:40] + ("…" if len(str(latest_msg.query)) > 40 else "")),
                "preview": latest_msg.preview or (str(latest_msg.query)[:60] + ("…" if len(str(latest_msg.query)) > 60 else "")),
                "message_count": count,
                "last_query": str(latest_msg.query)[:60],
                "is_pinned": bool(latest_msg.is_pinned),
                "created_at": conv.created_at.isoformat() if conv.created_at is not None else None,
                "updated_at": conv.updated_at.isoformat() if conv.updated_at is not None else None,
            })
        return result

    # ─── Get all messages for a session ──────────────────────────────────────

    def get_by_session(self, user_id: int, session_id: str) -> List[ChatHistory]:
        sid: Any = session_id
        try:
            sid = uuid.UUID(session_id)
        except ValueError:
            pass

        return (
            self.db.query(ChatHistory)
            .filter(ChatHistory.user_id == user_id, ChatHistory.conversation_id == sid)
            .order_by(ChatHistory.created_at.asc())
            .all()
        )  # type: ignore

    # ─── Get recent messages (flat, for legacy use) ───────────────────────────

    def get_recent(self, user_id: int, limit: int = 100) -> List[ChatHistory]:
        return (
            self.db.query(ChatHistory)
            .filter(ChatHistory.user_id == user_id)
            .order_by(ChatHistory.created_at.desc())
            .limit(limit)
            .all()
        )  # type: ignore

    # ─── Rename a chat session ────────────────────────────────────────────────

    def rename_session(self, user_id: int, session_id: str, new_title: str) -> bool:
        sid: Any = session_id
        try:
            sid = uuid.UUID(session_id)
        except ValueError:
            return False

        updated = (
            self.db.query(ChatHistory)
            .filter(ChatHistory.user_id == user_id, ChatHistory.session_id == sid)
            .update({"title": new_title[:120]})
        )
        self.db.commit()
        return updated > 0

    # ─── Delete a chat session ────────────────────────────────────────────────

    def delete_session(self, user_id: int, session_id: str) -> bool:
        sid: Any = session_id
        try:
            sid = uuid.UUID(session_id)
        except ValueError:
            return False

        deleted = (
            self.db.query(ChatHistory)
            .filter(ChatHistory.user_id == user_id, ChatHistory.session_id == sid)
            .delete()
        )
        self.db.commit()
        return deleted > 0

    # ─── Pin a chat session ───────────────────────────────────────────────────

    def pin_session(self, user_id: int, session_id: str, pinned: bool) -> bool:
        sid: Any = session_id
        try:
            sid = uuid.UUID(session_id)
        except ValueError:
            return False

        updated = (
            self.db.query(ChatHistory)
            .filter(ChatHistory.user_id == user_id, ChatHistory.session_id == sid)
            .update({"is_pinned": 1 if pinned else 0})
        )
        self.db.commit()
        return updated > 0

    # ─── Bulk delete sessions ─────────────────────────────────────────────────

    def bulk_delete(self, user_id: int, session_ids: List[str]) -> int:
        sids = []
        for sid_str in session_ids:
            try:
                sids.append(uuid.UUID(sid_str))
            except ValueError:
                continue

        if not sids:
            return 0

        deleted = (
            self.db.query(ChatHistory)
            .filter(ChatHistory.user_id == user_id, ChatHistory.session_id.in_(sids))
            .delete(synchronize_session=False)
        )
        self.db.commit()
        return deleted

    # ─── Update answer specifically (for streaming sync) ─────────────────────

    def update_answer(self, record_id: int, answer: str, source: Optional[str] = None, confidence: Optional[int] = None):
        data = {ChatHistory.answer: answer, ChatHistory.updated_at: func.now()}
        if source:
            data[ChatHistory.source] = source
        if confidence is not None:
            data[ChatHistory.confidence] = confidence
            
        self.db.query(ChatHistory).filter(ChatHistory.id == record_id).update(data)
        self.db.commit()

    # ─── Check if session has any messages (for auto-title trigger) ───────────

    def is_first_message(self, user_id: int, session_id: str) -> bool:
        sid: Any = session_id
        try:
            sid = uuid.UUID(session_id)
        except ValueError:
            return False

        count = (
            self.db.query(func.count(ChatHistory.id))
            .filter(ChatHistory.user_id == user_id, ChatHistory.conversation_id == sid)
            .scalar()
            or 0
        )
        return count == 0
