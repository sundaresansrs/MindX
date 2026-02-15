
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.quality_pipeline import QualityPipeline
from app.schemas import QAInput, QAOutput

router = APIRouter()

pipeline = QualityPipeline()

@router.post("/qa/", response_model=QAOutput)
def answer_question(qa_input: QAInput, db: Session = Depends(get_db)):
    try:
        answer = pipeline.run(qa_input.query)
        return QAOutput(answer=answer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
