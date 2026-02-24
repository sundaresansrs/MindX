from pydantic import BaseModel
from typing import Optional, List

class Token(BaseModel):
    access_token: str
    token_type: str
    user_id: Optional[int] = None
    full_name: Optional[str] = None

class UserCreate(BaseModel):
    email: str
    password: str
    account_type: str
    company_name: Optional[str] = None
    access_level: Optional[str] = None
    full_name: str


class QAInput(BaseModel):
    query: str
    use_search: bool = True  # Enable/disable web search
    max_sources: int = 20    # Maximum sources to include

class QAOutput(BaseModel):
    answer: str
    sources: List[dict]  # List of {title, url, snippet, source}
    confidence: float
    metadata: dict

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
