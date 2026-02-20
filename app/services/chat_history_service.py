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

        # Count existing messages and versions
        existing_count = 0
        latest_version = 0
        if sid:
            existing_count = (
                self.db.query(func.count(ChatHistory.id))
                .filter(ChatHistory.user_id == user_id, ChatHistory.session_id == sid)
                .scalar()
                or 0
            )
            latest_version = (
                self.db.query(func.max(ChatHistory.version))
                .filter(ChatHistory.user_id == user_id, ChatHistory.session_id == sid, ChatHistory.query == query)
                .scalar()
                or 0
            )

        record = ChatHistory(
            user_id=user_id,
            query=query,
            answer=answer,
            source=source,
            session_id=sid,
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

        self.db.query(ChatHistory).filter(
            ChatHistory.user_id == user_id,
            ChatHistory.session_id == sid,
        ).update({"title": title})
        self.db.commit()

    # ─── Get session list (one entry per session, most recent first) ──────────

    def get_sessions_list(self, user_id: int, limit: int = 100) -> List[Dict]:
        """
        Returns one row per session_id: the most recent message row.
        Groups by session_id and sorts by is_pinned and updated_at.
        """
        # Subquery: latest id per session
        subq = (
            self.db.query(func.max(ChatHistory.id).label("max_id"))
            .filter(ChatHistory.user_id == user_id, ChatHistory.session_id.isnot(None))
            .group_by(ChatHistory.session_id)
            .subquery()
        )
        rows = (
            self.db.query(ChatHistory)
            .join(subq, ChatHistory.id == subq.c.max_id)
            .order_by(desc(ChatHistory.is_pinned), desc(ChatHistory.updated_at))
            .limit(limit)
            .all()
        )

        result = []
        for row in rows:
            # Get total message count for this session
            count = (
                self.db.query(func.count(ChatHistory.id))
                .filter(
                    ChatHistory.user_id == user_id,
                    ChatHistory.session_id == row.session_id,
                )
                .scalar()
                or 0
            )
            result.append({
                "session_id": str(row.session_id),
                "title": row.title or (row.query[:40] + ("…" if len(row.query) > 40 else "")),
                "preview": row.preview or (row.query[:60] + ("…" if len(row.query) > 60 else "")),
                "message_count": count,
                "last_query": row.query[:60],
                "is_pinned": bool(row.is_pinned),
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
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
            .filter(ChatHistory.user_id == user_id, ChatHistory.session_id == sid)
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
        data: Dict[str, Any] = {"answer": answer, "updated_at": func.now()}
        if source:
            data["source"] = source
        if confidence is not None:
            data["confidence"] = confidence
            
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
            .filter(ChatHistory.user_id == user_id, ChatHistory.session_id == sid)
            .scalar()
            or 0
        )
        return count == 0
