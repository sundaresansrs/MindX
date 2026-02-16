from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.schemas import QAInput
from app.database import get_db
from app.routers.auth import get_current_user
from app.services.pipeline_factory import PipelineFactory

router = APIRouter(prefix="/qa", tags=["qa"])


@router.post("/")
async def ask_question(
    payload: QAInput,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pipeline = PipelineFactory.get_pipeline(
        user=current_user,
        db=db,
    )

    return await pipeline.process(payload.query)
