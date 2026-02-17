from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import select, text
from pydantic import BaseModel
from typing import List, Optional
import requests

from app.database import get_db
from app.models.document import Document
from app.routers.auth import get_current_user
from app.services.embeddings import EmbeddingsService
from app.services.upload_service import UploadService
from app.services.vector_service import VectorService


router = APIRouter(
    prefix="/documents",
    tags=["documents"]
)

embeddings_service = EmbeddingsService()

class DocumentIngest(BaseModel):
    url: Optional[str] = None
    text: Optional[str] = None

class SearchQuery(BaseModel):
    query: str
    limit: int = 5

class DocumentResponse(BaseModel):
    id: str
    content: str
    source_url: Optional[str] = None
    score: Optional[float] = None

@router.post("/ingest", response_model=DocumentResponse)
async def ingest_document(
    doc: DocumentIngest, 
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    content = doc.text
    if doc.url:
        # Use Jina Reader to get content if URL provided
        try:
            reader_url = f"https://r.jina.ai/{doc.url}"
            resp = requests.get(reader_url)
            if resp.status_code == 200:
                content = resp.text
            else:
                raise HTTPException(status_code=400, detail="Failed to fetch content from URL")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error processing URL: {str(e)}")
    
    if not content:
        # Fallback to empty if both url and text are missing
        raise HTTPException(status_code=400, detail="No content provided")

    # Generate embedding
    embedding = embeddings_service.get_embeddings([content])[0]
    
    # Save to DB - now with user_id!
    new_doc = Document(
        content=content,
        source_url=doc.url,
        embedding=embedding,
        user_id=current_user.id
    )
    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)

    
    return DocumentResponse(
        id=str(new_doc.id),
        content=new_doc.content[:200] + "...", # Truncate for response
        source_url=new_doc.source_url
    )

@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    session_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Upload and parse a document (Word, PPT, Excel, etc.)
    """
    try:
        content = await file.read()
        filename = file.filename
        
        # Parse content based on file type
        parser = UploadService()
        parsed_text = parser.parse_file(content, filename)
        
        if not parsed_text or parsed_text.startswith("Error parsing") or parsed_text.startswith("Unsupported"):
             raise HTTPException(status_code=400, detail=parsed_text)

        # Index via VectorService
        vector_service = VectorService(db)
        new_doc = await vector_service.ingest_document(
            content=parsed_text,
            user_id=current_user.id,
            source_url=filename,
            session_id=session_id
        )
        
        return DocumentResponse(
            id=str(new_doc.id),
            content=new_doc.content[:200] + "...",
            source_url=new_doc.source_url
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@router.post("/search", response_model=List[DocumentResponse])
async def search_documents(
    query: SearchQuery, 
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # Generate query embedding
    query_vec = embeddings_service.get_embeddings([query.query])[0]
    
    try:
        results = db.scalars(
            select(Document)
            .where(Document.user_id == current_user.id) # 🔐 Filter by current user
            .order_by(Document.embedding.cosine_distance(query_vec))
            .limit(query.limit)
        ).all()
        
        return [
            DocumentResponse(
                id=str(doc.id),
                content=doc.content,
                source_url=doc.source_url,
                score=0.0 
            )
            for doc in results
        ]
    except Exception as e:
        print(f"Search Error: {e}")
        # Build fallback search using text matching if vector fails
        results = db.scalars(
            select(Document)
            .where(Document.user_id == current_user.id) # 🔐 Filter by current user
            .where(Document.content.ilike(f"%{query.query}%"))
            .limit(query.limit)
        ).all()
        return [
            DocumentResponse(
                id=str(doc.id),
                content=doc.content,
                source_url=doc.source_url,
                score=0.0
            )
            for doc in results
        ]

