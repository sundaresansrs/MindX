
from pydantic import BaseModel
from typing import Optional

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class User(BaseModel):
    username: str

class UserCreate(User):
    password: str

class QAInput(BaseModel):
    query: str

class QAOutput(BaseModel):
    answer: str
