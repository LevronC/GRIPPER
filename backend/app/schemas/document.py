from pydantic import BaseModel, Field

class SemanticSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Semantic search query string")
    limit: int = Field(5, ge=1, le=20, description="Max search results to return")
