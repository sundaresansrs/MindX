from pydantic import BaseModel
from typing import Optional, List

class Token(BaseModel):
    access_token: str
    token_type: str

class UserCreate(BaseModel):
    email: str
    password: str
    account_type: str
    company_name: Optional[str] = None

class QAInput(BaseModel):
    query: str

class QAOutput(BaseModel):
    answer: str
    sources: List[str]
