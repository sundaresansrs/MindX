from fastapi import FastAPI
from app.routers import auth, qa
from app.database import engine, Base

# Create FastAPI app
app = FastAPI(title="MindX API")

# Create database tables
Base.metadata.create_all(bind=engine)

# Register routers
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(qa.router, prefix="/qa", tags=["QA"])

@app.get("/health", tags=["Health"])
def health():
    return {
        "status": "ok",
        "llm": "groq",
        "env_loaded": True
    }

@app.get("/", tags=["Root"])
def read_root():
    return {"message": "Welcome to the RAG-based QA system"}
