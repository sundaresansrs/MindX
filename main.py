from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, qa, documents
from app.database import engine, Base
import app.models.user
import app.models.chat_history


import os

app = FastAPI(title="MindX API", version="1.0.0")

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


# Serve frontend HTML pages
@app.get("/")
def landing_page():
    return FileResponse("public/index.html")


@app.get("/login.html")
def login_page():
    return FileResponse("public/login.html")


@app.get("/signup.html")
def signup_page():
    return FileResponse("public/signup.html")


@app.get("/dashboard.html")
def dashboard_page():
    return FileResponse("public/dashboard.html")


# Serve static assets (CSS, JS, images)
app.mount("/static", StaticFiles(directory="static"), name="static")
