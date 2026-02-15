
from fastapi import FastAPI
from app.database import Base, engine

# Create all tables
Base.metadata.create_all(bind=engine)

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Welcome to the FastAPI application!"}
