from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.routers.auth import get_current_user
from app.services.pipeline_factory import PipelineFactory

router = APIRouter(tags=["qa"])

class SearchRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    use_search: Optional[bool] = True
    max_sources: Optional[int] = 10
    fast_mode: Optional[bool] = False
    file_ids: Optional[list[str]] = None


from fastapi.responses import StreamingResponse
import json

@router.post("/search")
async def search(request: SearchRequest, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    # ✅ STRICT OWNERSHIP CHECK
    if request.session_id:
        from app.models.conversation import Conversation
        conv = db.query(Conversation).filter(
            Conversation.id == request.session_id,
            Conversation.user_id == current_user.id
        ).first()
        if not conv:
             raise HTTPException(status_code=403, detail="Access denied to this chat session")

    # Factory expects (user, db)
    pipeline = PipelineFactory.get_pipeline(current_user, db)
    result = await pipeline.search(
        query=request.query, 
        session_id=request.session_id,  # type: ignore
        use_search=request.use_search or True,  # type: ignore
        max_sources=request.max_sources or 10,  # type: ignore
        fast_mode=request.fast_mode or False,  # type: ignore
        file_ids=request.file_ids
    )
    return result

@router.post("/stream")
async def stream_search(request: SearchRequest, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    # ✅ STRICT OWNERSHIP CHECK
    if request.session_id:
        from app.models.conversation import Conversation
        conv = db.query(Conversation).filter(
            Conversation.id == request.session_id,
            Conversation.user_id == current_user.id
        ).first()
        if not conv:
             raise HTTPException(status_code=403, detail="Access denied to this chat session")

    pipeline = PipelineFactory.get_pipeline(current_user, db)
    
    async def event_generator():
        async for chunk in pipeline.stream(
            query=request.query,
            session_id=request.session_id,  # type: ignore
            use_search=request.use_search or True,  # type: ignore
            max_sources=request.max_sources or 10,  # type: ignore
            fast_mode=request.fast_mode or False,  # type: ignore
            file_ids=request.file_ids
        ):
            yield f"data: {json.dumps(chunk)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")




class FollowUpRequest(BaseModel):
    question: str
    answer: str

@router.post("/followups")
async def get_followups(
    request: FollowUpRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Generate 3 follow-up question suggestions based on the Q&A."""
    try:
        from app.services.llm_service import LLMService
        import json as _json, re as _re
        llm = LLMService()
        q = str(request.question)[:200]  # type: ignore
        a = str(request.answer)[:400]    # type: ignore
        prompt = (
            f"Based on this Q&A, suggest exactly 3 short follow-up questions the user might ask next.\n"
            f"Question: {q}\n"
            f"Answer summary: {a}\n\n"
            f"Return ONLY a JSON array of 3 strings, no explanation. Example: [\"Q1?\", \"Q2?\", \"Q3?\"]"
        )
        raw = await llm.generate_response(prompt=prompt)
        # Extract JSON array from response
        match = _re.search(r'\[.*?\]', raw, _re.DOTALL)
        if match:
            suggestions = _json.loads(match.group())
            return {"suggestions": suggestions[:3]}
    except Exception:
        pass
    return {"suggestions": []}


@router.get("/history")
def get_history(
    session_id: Optional[str] = None,
    limit: int = 10,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get recent chat history for the current user
    """
    from app.services.chat_history_service import ChatHistoryService
    service = ChatHistoryService(db)
    
    if session_id:
        # ✅ STRICT OWNERSHIP CHECK inside service.get_by_session
        from app.models.conversation import Conversation
        conv = db.query(Conversation).filter(
            Conversation.id == session_id,
            Conversation.user_id == current_user.id
        ).first()
        if not conv:
             raise HTTPException(status_code=403, detail="Access denied")
             
        history = service.get_by_session(user_id=current_user.id, session_id=session_id)
    else:
        history = service.get_recent(user_id=current_user.id, limit=limit)
    
    return history


