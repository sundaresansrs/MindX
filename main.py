from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, qa, documents
from app.database import engine, Base
import app.models.user
import app.models.chat_history
import app.models.document



import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

import logging
import traceback
from pathlib import Path

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent

from fastapi.responses import JSONResponse


# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="MindX API", version="1.0.0")


# Catch-all error middleware for easier debugging on Vercel
@app.middleware("http")
async def catch_exceptions_middleware(request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        logger.error(f"Unhandled Exception: {e}\n{traceback.format_exc()}")
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "type": type(e).__name__,
                "detail": "Internal Server Error. Please check backend logs."
            }
        )

# CORS - allow frontend to call API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
app.include_router(auth.router)
app.include_router(qa.router)
app.include_router(documents.router)

@app.on_event("startup")
def on_startup():
    try:
        from sqlalchemy import text
        print("Creating database tables and enabling vector extension...")
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            conn.commit()
        Base.metadata.create_all(bind=engine)
        print("Database ready.")
    except Exception as e:
        print(f"Database initialization failed: {e}")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "llm": "groq",
        "env_loaded": True,
    }

@app.get("/")
def landing_page():
    index_path = BASE_DIR / "public" / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return JSONResponse(status_code=404, content={"error": "index.html not found"})

@app.get("/login.html")
def login_page():
    return FileResponse(BASE_DIR / "public" / "login.html")

@app.get("/signup.html")
def signup_page():
    return FileResponse(BASE_DIR / "public" / "signup.html")

@app.get("/dashboard.html")
def dashboard_page():
    return FileResponse(BASE_DIR / "public" / "dashboard.html")

# Serve static assets (CSS, JS, images)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")



