from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.schemas import QAInput
from app.database import get_db
from app.routers.auth import get_current_user
from app.services.pipeline_factory import PipelineFactory

router = APIRouter(prefix="/qa", tags=["qa"])


@router.post("/search")
async def ask_question(
    payload: QAInput,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Ask a question and get an AI-generated answer
    """
    try:
        pipeline = PipelineFactory.get_pipeline(
            user=current_user,
            db=db,
        )

        return await pipeline.process(
            query=payload.query,
            use_search=payload.use_search,
            max_sources=payload.max_sources
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
def get_history(
    limit: int = 10,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get recent chat history for the current user
    """
    from app.services.chat_history_service import ChatHistoryService
    service = ChatHistoryService(db)
    history = service.get_recent(user_id=current_user.id, limit=limit)
    return history


