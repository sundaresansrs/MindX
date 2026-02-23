from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, qa, documents, chats, voice, upload
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
    # Specialized handling for streaming endpoints to avoid JSONResponse errors
    if request.url.path.endswith("/stream"):
        return await call_next(request)
        
    try:
        return await call_next(request)
    except Exception as e:
        logger.error(f"Unhandled Exception in {request.url.path}: {e}\n{traceback.format_exc()}")
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "type": type(e).__name__,
                "detail": "Internal Server Error"
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

app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(qa.router, prefix="/api", tags=["QA"])
app.include_router(documents.router, prefix="/api", tags=["Documents"])
app.include_router(chats.router, prefix="/chats", tags=["Chats"])
app.include_router(voice.router, prefix="/api", tags=["Voice"])
app.include_router(upload.router, prefix="/api", tags=["Upload"])


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

# Dedicated routes for landing and app pages if they need specific logic
# Otherwise the static mount at "/" will handle them automatically.
@app.get("/")
def landing_page():
    return FileResponse(BASE_DIR / "public" / "index.html")

# Redirect old V2 users to the unified dashboard
@app.get("/dashboard_v2.html")
def dashboard_v2_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/dashboard.html")


# Serve static assets (CSS, JS, images)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Serve public assets (config.js, script.js) at the root
# Must be mounted last so explicit routes (/login, /dashboard) take priority
app.mount("/", StaticFiles(directory=str(BASE_DIR / "public")), name="public")
