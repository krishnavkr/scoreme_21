import uuid
import uvicorn
from fastapi import FastAPI, Depends, Header, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Optional
from pathlib import Path

from app.models.domain import init_db, get_db, WorkflowIntakeRequest, RequestState, AuditLog
from app.engine.orchestrator import WorkflowOrchestrator

# Initialize the SQLite database
init_db()

app = FastAPI(
    title="Configurable Workflow Decision Platform",
    description="A resilient engine for evaluating business rules and handling workflows.",
    version="1.0.0"
)

# Resolve absolute path for static files so it works regardless of where uvicorn is run from
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

# Serve the static UI files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
async def serve_frontend():
    """Serves the user-friendly frontend."""
    return FileResponse(str(STATIC_DIR / "index.html"))

@app.post("/api/v1/workflow/evaluate")
async def evaluate_workflow(
    request: WorkflowIntakeRequest,
    idempotency_key: Optional[str] = Header(None, description="Unique key to prevent duplicate processing"),
    db: Session = Depends(get_db)
):
    """
    Intake endpoint for submitting requests into the decision platform.
    """
    request_id = str(uuid.uuid4())
    orchestrator = WorkflowOrchestrator(db)
    
    try:
        response = await orchestrator.execute(
            request_id=request_id,
            workflow_name=request.workflow_name,
            payload=request.payload,
            idempotency_key=idempotency_key
        )
        return response
    except Exception as e:
        # Catch unexpected errors to prevent API crashes, though the orchestrator handles most workflow failures
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/workflow/{request_id}/status")
async def get_workflow_status(request_id: str, db: Session = Depends(get_db)):
    """
    Returns the current state of a given workflow request.
    """
    state = db.query(RequestState).filter(RequestState.id == request_id).first()
    if not state:
        raise HTTPException(status_code=404, detail="Request state not found")
        
    return {
        "request_id": state.id,
        "workflow_name": state.workflow_name,
        "current_stage": state.current_stage,
        "created_at": state.created_at,
        "updated_at": state.updated_at
    }

@app.get("/api/v1/workflow/{request_id}/audit")
async def get_workflow_audit_trail(request_id: str, db: Session = Depends(get_db)):
    """
    Retrieve the full decision explanation and audit trail.
    """
    logs = db.query(AuditLog).filter(AuditLog.request_id == request_id).order_by(AuditLog.timestamp).all()
    if not logs:
        raise HTTPException(status_code=404, detail="No audit logs found for this request")
        
    return [
        {
            "timestamp": log.timestamp,
            "event_type": log.event_type,
            "details": log.details
        }
        for log in logs
    ]

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
