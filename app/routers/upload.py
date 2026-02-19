from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from app.services.file_processor import FileProcessor
from app.services.vector_service import VectorService
from app.services.web_search import WebSearchService
from app.services.groq_client import GroqClient
import shutil
import os
import uuid
import logging
from typing import List, Optional

router = APIRouter()
logger = logging.getLogger(__name__)

# Temporary storage for uploaded files chunks (In production, use Redis or DB)
# Structure: { file_id: { "chunks": [], "metadata": {} } }
UPLOADED_FILES_CACHE = {}

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Processes an uploaded file and returns its ID and basic metadata.
    """
    file_id = str(uuid.uuid4())
    temp_filename = f"temp_{file_id}_{file.filename}"
    
    try:
        # Read file content
        content = await file.read()
        
        # Process file using our service
        result = await FileProcessor.process_file(content, file.filename)
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Unknown error"))
            
        # Store processed data in cache
        UPLOADED_FILES_CACHE[file_id] = {
            "filename": file.filename,
            "type": result.get("type"),
            "text": result.get("text"),
            "chunks": result.get("chunks", []),
            "metadata": {
                "page_count": result.get("page_count"),
                "sheet_count": len(result.get("sheets", [])) if "sheets" in result else 0
            }
        }
        
        return {
            "file_id": file_id,
            "filename": file.filename,
            "success": True,
            "message": "File processed successfully",
            "type": result.get("type"),
            "preview": result.get("text")[:200] + "..." if result.get("text") else ""
        }
        
    except Exception as e:
        logger.error(f"File upload error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/chat-with-file")
async def chat_with_file(
    message: str = Form(...),
    file_id: str = Form(...),
    model: str = Form("llama3-70b-8192")
):
    """
    RAG Endpoint: Chat specifically with an uploaded file.
    """
    if file_id not in UPLOADED_FILES_CACHE:
        raise HTTPException(status_code=404, detail="File session identifier not found or expired")
        
    file_data = UPLOADED_FILES_CACHE[file_id]
    
    # 1. Retrieve relevant chunks based on query
    relevant_context = ""
    
    if file_data.get("chunks"):
        # Simple keyword/semantic search within the file chunks
        # In a real app, these would be indexed in a vector DB
        # For now, we perform a linear scan with keyword overlap scoring
        scored_chunks = []
        query_terms = set(message.lower().split())
        
        for chunk in file_data["chunks"]:
            score = 0
            chunk_text_lower = chunk["text"].lower()
            for term in query_terms:
                if term in chunk_text_lower:
                    score += 1
            scored_chunks.append((score, chunk["text"]))
            
        # Sort by score and take top 5
        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        top_chunks = [c[1] for c in scored_chunks[:5] if c[0] > 0]
        
        if not top_chunks and file_data.get("text"):
             # Fallback: if no keywords match, take first 2000 chars
             relevant_context = file_data["text"][:3000]
        else:
             relevant_context = "\n---\n".join(top_chunks)
    else:
        # Fallback for small files (images/short text)
        relevant_context = file_data.get("text", "")[:5000]

    # 2. Construct Prompt
    system_prompt = f"""You are analyzing a file named '{file_data['filename']}'.
User Question: {message}

Relevant File Context:
{relevant_context}

Instructions:
1. Answer the user's question explicitly based on the file context provided.
2. If the answer is not in the file, state that clearly.
3. specific details from the file (numbers, quotes, specific data points).
"""

    # 3. Call LLM
    try:
        response = await GroqClient.chat_completion(
            messages=[{"role": "user", "content": system_prompt}],
            model=model,
            temperature=0.3
        )
        return {
            "answer": response["content"],
            "sources": [{"source": f"File: {file_data['filename']}", "snippet": "Context from uploaded file"}]
        }
    except Exception as e:
        logger.error(f"Chat with file error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
