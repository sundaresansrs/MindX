from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, text
from pydantic import BaseModel
from typing import List, Optional
import requests

from app.database import get_db
from app.models.document import Document
from app.services.embeddings import EmbeddingsService

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
async def ingest_document(doc: DocumentIngest, db: Session = Depends(get_db)):
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
        raise HTTPException(status_code=400, detail="No content provided")

    # Generate embedding
    embedding = embeddings_service.get_embeddings([content])[0]
    
    # Save to DB
    new_doc = Document(
        content=content,
        source_url=doc.url,
        embedding=embedding
    )
    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)
    
    return DocumentResponse(
        id=str(new_doc.id),
        content=new_doc.content[:200] + "...", # Truncate for response
        source_url=new_doc.source_url
    )

@router.post("/search", response_model=List[DocumentResponse])
async def search_documents(query: SearchQuery, db: Session = Depends(get_db)):
    # Generate query embedding
    query_vec = embeddings_service.get_embeddings([query.query])[0]
    
    # Search using pgvector cosine distance (<=>) or L2 (<->) or Inner Product (<#>)
    # For normalized embeddings, cosine and inner product are similar. Jina matches cosine.
    # <=> is cosine distance operator in pgvector
    
    # We use raw SQL or SQLAlchemy expression with pgvector
    # Note: vector extension must be enabled
    
    try:
        results = db.scalars(
            select(Document)
            .order_by(Document.embedding.cosine_distance(query_vec))
            .limit(query.limit)
        ).all()
        
        # Calculate score (1 - distance) manually or return distance?
        # For simplicity, returning the document. Score needs distance calculation in query.
        
        return [
            DocumentResponse(
                id=str(doc.id),
                content=doc.content,
                source_url=doc.source_url,
                score=0.0 # Placeholder as we didn't fetch distance
            )
            for doc in results
        ]
    except Exception as e:
        print(f"Search Error: {e}")
        # Build fallback search using text matching if vector fails
        results = db.scalars(
            select(Document)
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
