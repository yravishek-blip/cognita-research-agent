import os
import json
import logging
from typing import Dict, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from engine.models import ResearchRequest, ResearchReport, ResearchProgressEvent
from engine.agent import DeepResearchAgent
from engine.llm import LLMService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("cognita")

app = FastAPI(
    title="Cognita - Autonomous Deep Research Engine",
    description="Self-directed multi-source intelligence agent",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage for active session reports
saved_reports: Dict[str, ResearchReport] = {}

# Ensure static and templates folders exist
os.makedirs("static/css", exist_ok=True)
os.makedirs("static/js", exist_ok=True)
os.makedirs("templates", exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = os.path.join("templates", "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Cognita Engine Initializing...</h1>"

@app.get("/api/providers")
async def get_providers_status():
    """Check configuration and active LLM engines."""
    return {
        "gemini": bool(os.getenv("GEMINI_API_KEY")),
        "openai": bool(os.getenv("OPENAI_API_KEY")),
        "groq": bool(os.getenv("GROQ_API_KEY")),
        "ollama": os.getenv("OLLAMA_ENABLED", "false").lower() == "true",
        "active_default": LLMService().active_provider
    }

@app.get("/api/reports", response_model=List[dict])
async def list_reports():
    """List recent research reports."""
    return [
        {
            "id": r.id,
            "topic": r.topic,
            "timestamp": r.timestamp,
            "total_words": r.total_words,
            "total_sources": r.total_sources_scanned,
            "depth": r.depth
        }
        for r in saved_reports.values()
    ]

@app.get("/api/reports/{report_id}", response_model=ResearchReport)
async def get_report(report_id: str):
    """Retrieve full report by ID."""
    if report_id not in saved_reports:
        raise HTTPException(status_code=404, detail="Report not found")
    return saved_reports[report_id]

@app.get("/api/export/{report_id}/markdown", response_class=PlainTextResponse)
async def export_markdown(report_id: str):
    """Download research report as a raw Markdown file."""
    if report_id not in saved_reports:
        raise HTTPException(status_code=404, detail="Report not found")
    report = saved_reports[report_id]
    return PlainTextResponse(
        content=report.markdown_report,
        headers={
            "Content-Disposition": f"attachment; filename=cognita_briefing_{report_id}.md"
        }
    )

@app.websocket("/ws/research")
async def websocket_research(websocket: WebSocket):
    """
    WebSocket endpoint that streams autonomous research progress in real-time.
    """
    await websocket.accept()
    logger.info("WebSocket research client connected.")

    try:
        # Await initial research request
        data = await websocket.receive_text()
        request_dict = json.loads(data)
        request = ResearchRequest(**request_dict)

        async def send_event(event: ResearchProgressEvent):
            try:
                await websocket.send_json(event.dict())
            except Exception as e:
                logger.warning(f"Failed to send event to WebSocket: {e}")

        # Initialize agent with callback
        agent = DeepResearchAgent(request=request, event_callback=send_event)

        # Run research lifecycle
        report = await agent.execute()

        # Cache report
        saved_reports[report.id] = report

        # Send completion event with full report payload
        await websocket.send_json({
            "step": "final_report",
            "phase_title": "Report Available",
            "message": "Mission complete. Transmitting full intelligence briefing.",
            "progress": 100,
            "report": report.dict()
        })

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected.")
    except Exception as e:
        logger.error(f"Error in research session: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "step": "error",
                "phase_title": "Execution Interrupted",
                "message": f"Research halted: {str(e)}",
                "progress": 0
            })
        except Exception:
            pass

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
