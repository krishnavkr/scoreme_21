import json
from loguru import logger
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional

from app.models.domain import RequestState, AuditLog, IdempotencyRecord
import logging
logger = logging.getLogger(__name__)

class Repository:
    """Abstracts database transactions away from the core logic."""

    def __init__(self, db: Session):
        self.db = db

    def create_idempotency_record(self, request_id: str, idempotency_key: str) -> bool:
        """
        Attempts to create an idempotency lock. 
        Returns True if successful, False if key already exists.
        """
        try:
            record = IdempotencyRecord(
                idempotency_key=idempotency_key,
                request_id=request_id,
                status="IN_PROGRESS"
            )
            self.db.add(record)
            self.db.commit()
            return True
        except IntegrityError:
            self.db.rollback()
            return False

    def get_idempotency_record(self, idempotency_key: str) -> Optional[IdempotencyRecord]:
        return self.db.query(IdempotencyRecord).filter(IdempotencyRecord.idempotency_key == idempotency_key).first()
        
    def complete_idempotency_record(self, idempotency_key: str, response_payload: dict):
        record = self.get_idempotency_record(idempotency_key)
        if record:
            record.status = "COMPLETED"
            record.response_payload = response_payload
            self.db.commit()

    def get_state(self, request_id: str) -> Optional[RequestState]:
        return self.db.query(RequestState).filter(RequestState.id == request_id).first()

    def update_state(self, request_id: str, current_stage: str, enriched_data: dict = None) -> RequestState:
        state = self.get_state(request_id)
        if not state:
            raise ValueError(f"State not found for request_id: {request_id}")
            
        state.current_stage = current_stage
        if enriched_data:
            state.enriched_data.update(enriched_data)
        
        self.db.commit()
        self.db.refresh(state)
        return state

    def create_initial_state(self, request_id: str, workflow_name: str, payload: dict) -> RequestState:
        state = RequestState(
            id=request_id,
            workflow_name=workflow_name,
            current_stage="PENDING", # All workflows start at PENDING
            payload=payload
        )
        self.db.add(state)
        self.db.commit()
        return state

    def log_audit_event(self, request_id: str, event_type: str, details: dict):
        log = AuditLog(
            request_id=request_id,
            event_type=event_type,
            details=details
        )
        self.db.add(log)
        self.db.commit()
