from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class ResearchRequest(BaseModel):
    query: str = Field(..., description="The main research question or topic")
    depth: str = Field(default="deep", description="Research depth: 'quick', 'deep', or 'exhaustive'")
    breadth: int = Field(default=4, ge=2, le=8, description="Number of sub-queries to decompose into")
    provider: str = Field(default="auto", description="LLM provider: 'auto', 'gemini', 'openai', 'groq', 'ollama', or 'local'")
    api_key: Optional[str] = Field(default=None, description="Optional runtime API key override")

class SubQuery(BaseModel):
    id: int
    query: str
    rationale: str
    status: str = "pending"  # pending, searching, completed, failed

class ScrapedDocument(BaseModel):
    url: str
    title: str
    snippet: str
    raw_content: Optional[str] = None
    clean_text: Optional[str] = None
    domain: str
    char_count: int = 0
    credibility_score: float = 0.5  # 0.0 to 1.0
    credibility_reasons: List[str] = Field(default_factory=list)

class SourceEvidence(BaseModel):
    citation_id: int
    url: str
    title: str
    domain: str
    credibility_score: float
    key_findings: List[str] = Field(default_factory=list)

class ResearchProgressEvent(BaseModel):
    step: str  # planning, searching, scraping, analyzing, synthesizing, completed, error
    phase_title: str
    message: str
    progress: int  # 0 to 100
    data: Optional[Dict[str, Any]] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())

class ResearchReport(BaseModel):
    id: str
    topic: str
    timestamp: str
    executive_summary: str
    markdown_report: str
    sub_queries: List[SubQuery] = Field(default_factory=list)
    sources: List[SourceEvidence] = Field(default_factory=list)
    total_sources_scanned: int = 0
    total_words: int = 0
    depth: str = "deep"
