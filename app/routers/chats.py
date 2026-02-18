"""
/chats router — Claude-style chat session management
Endpoints:
  GET    /chats              → list all sessions grouped by date
  GET    /chats/{id}         → load all messages for a session
  PATCH  /chats/{id}         → rename a chat
  DELETE /chats/{id}         → delete a chat and all its messages
  POST   /chats/{id}/title   → trigger/update auto-title
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

from app.database import get_db
from app.routers.auth import get_current_user
from app.services.chat_history_service import ChatHistoryService

router = APIRouter(prefix="/chats", tags=["chats"])


# ─── Schemas ─────────────────────────────────────────────────────────────────

class RenameRequest(BaseModel):
    title: str

class TitleRequest(BaseModel):
    title: str

class PinRequest(BaseModel):
    pinned: bool

class BulkDeleteRequest(BaseModel):
    session_ids: List[str]


# ─── Helper: group sessions by date bucket ────────────────────────────────────

def _date_bucket(iso_str: Optional[str]) -> str:
    if not iso_str:
        return "Older"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = (now - dt).days
        if diff == 0:
            return "Today"
        elif diff == 1:
            return "Yesterday"
        elif diff <= 7:
            return "This Week"
        elif diff <= 30:
            return "Last Month"
        else:
            return "Older"
    except Exception:
        return "Older"


# ─── GET /chats ───────────────────────────────────────────────────────────────

@router.get("")
def list_chats(
    limit: int = 100,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all chat sessions grouped by date bucket (Today, Yesterday, etc.)"""
    service = ChatHistoryService(db)
    sessions = service.get_sessions_list(user_id=current_user.id, limit=limit)

    # Group by date bucket
    groups: dict = {
        "Today": [],
        "Yesterday": [],
        "This Week": [],
        "Last Month": [],
        "Older": [],
    }
    for s in sessions:
        bucket = _date_bucket(s.get("updated_at") or s.get("created_at"))
        groups[bucket].append(s)

    # Return only non-empty groups in order
    ordered = [
        {"label": label, "sessions": groups[label]}
        for label in ["Today", "Yesterday", "This Week", "Last Month", "Older"]
        if groups[label]
    ]
    return {"groups": ordered, "total": len(sessions)}


# ─── GET /chats/{id} ──────────────────────────────────────────────────────────

@router.get("/{session_id}")
def get_chat(
    session_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Load all messages for a specific chat session."""
    service = ChatHistoryService(db)
    messages = service.get_by_session(user_id=current_user.id, session_id=session_id)

    if not messages:
        raise HTTPException(status_code=404, detail="Chat session not found")

    return {
        "session_id": session_id,
        "title": messages[-1].title or messages[0].query[:40],
        "messages": [
            {
                "id": m.id,
                "role_user": m.query,
                "role_assistant": m.answer,
                "source": m.source,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
        "message_count": len(messages),
    }


# ─── PATCH /chats/{id} ────────────────────────────────────────────────────────

@router.patch("/{session_id}")
def rename_chat(
    session_id: str,
    body: RenameRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Rename a chat session."""
    if not body.title.strip():
        raise HTTPException(status_code=400, detail="Title cannot be empty")

    service = ChatHistoryService(db)
    ok = service.rename_session(
        user_id=current_user.id,
        session_id=session_id,
        new_title=body.title.strip(),
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return {"ok": True, "title": body.title.strip()}


# ─── PATCH /chats/{id}/pin ────────────────────────────────────────────────────

@router.patch("/{session_id}/pin")
def pin_chat(
    session_id: str,
    body: PinRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Pin or unpin a chat session."""
    service = ChatHistoryService(db)
    ok = service.pin_session(
        user_id=current_user.id,
        session_id=session_id,
        pinned=body.pinned,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return {"ok": True, "pinned": body.pinned}


# ─── DELETE /chats/{id} ───────────────────────────────────────────────────────

@router.delete("/{session_id}")
def delete_chat(
    session_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a chat session and all its messages."""
    service = ChatHistoryService(db)
    ok = service.delete_session(user_id=current_user.id, session_id=session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return {"ok": True, "deleted": session_id}


# ─── DELETE /chats (Bulk) ─────────────────────────────────────────────────────

@router.delete("")
def bulk_delete_chats(
    body: BulkDeleteRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete multiple chat sessions at once."""
    service = ChatHistoryService(db)
    count = service.bulk_delete(user_id=current_user.id, session_ids=body.session_ids)
    return {"ok": True, "deleted_count": count}


# ─── POST /chats/{id}/title ───────────────────────────────────────────────────

@router.post("/{session_id}/title")
def set_title(
    session_id: str,
    body: TitleRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Set or update the title for a chat session (called after auto-title generation)."""
    if not body.title.strip():
        raise HTTPException(status_code=400, detail="Title cannot be empty")

    service = ChatHistoryService(db)
    service.update_title(
        user_id=current_user.id,
        session_id=session_id,
        title=body.title.strip()[:120],
    )
    return {"ok": True, "title": body.title.strip()}
