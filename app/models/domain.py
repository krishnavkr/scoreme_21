import enum
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from sqlalchemy import Column, String, Integer, DateTime, JSON, Enum, Boolean, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

# --- SQLAlchemy Database Models ---

class StateEnum(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"

class RequestState(Base):
    """Stores the current state of a workflow execution."""
    __tablename__ = "request_states"
    
    id = Column(String, primary_key=True, index=True) # UUID
    workflow_name = Column(String, nullable=False, index=True)
    current_stage = Column(String, nullable=False) # Maps to config
    payload = Column(JSON, nullable=False) # original incoming request
    enriched_data = Column(JSON, default={}) # data fetched from external
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class AuditLog(Base):
    """Append-only table recording every state transition and rule evaluation."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    event_type = Column(String, nullable=False) # e.g., 'STATE_CHANGE', 'RULE_EVALUATION', 'EXTERNAL_CALL'
    details = Column(JSON, nullable=False) # e.g., {'from': 'PENDING', 'to': 'APPROVED', 'rules_trace': [...]}

class IdempotencyRecord(Base):
    """Tracks processed requests to prevent duplicate execution safely."""
    __tablename__ = "idempotency_records"

    idempotency_key = Column(String, primary_key=True, index=True)
    request_id = Column(String, nullable=False)
    status = Column(String, nullable=False) # 'IN_PROGRESS', 'COMPLETED'
    response_payload = Column(JSON, nullable=True) # Cached response if completed
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# --- Database Setup Helper ---
engine = create_engine(
    "sqlite:///./decision_platform.db", 
    connect_args={"check_same_thread": False} # Needed for SQLite with FastAPI
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- Pydantic API Models ---

class WorkflowIntakeRequest(BaseModel):
    """The generic structure for incoming evaluations."""
    workflow_name: str = Field(..., description="Name of the workflow config to use")
    payload: Dict[str, Any] = Field(..., description="The dynamic data describing the request")

class WorkflowResponse(BaseModel):
    """Standardized response back to the client."""
    request_id: str
    workflow_name: str
    current_stage: str
    status: str
    message: str

class RuleTrace(BaseModel):
    rule: Dict[str, Any]
    passed: bool
    actual_value: Any
