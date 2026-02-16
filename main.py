from fastapi import FastAPI
from app.routers import auth, qa
from app.database import engine, Base
from app import models

app = FastAPI()

app.include_router(auth.router)
app.include_router(qa.router)


@app.on_event("startup")
def on_startup():
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Database ready.")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "llm": "groq",
        "env_loaded": True,
    }


@app.get("/")
def read_root():
    return {"message": "Welcome to the RAG-based QA system"}
