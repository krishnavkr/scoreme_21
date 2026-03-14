import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.models.domain import Base, get_db
from app.engine.rule_evaluator import RuleEvaluator

# -- Database Setup for Testing --
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_decision_platform.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

# -- Fixtures --
@pytest.fixture(autouse=True)
def cleanup_db():
    """Clear database tables before each test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


# -- Tests: Rule Engine --
def test_rule_evaluator_leaf_node_pass():
    rule = {"field": "score", "operator": ">=", "value": 700}
    context = {"score": 750}
    passed, trace = RuleEvaluator.evaluate_rule(rule, context)
    assert passed is True
    assert trace["actual_value"] == 750

def test_rule_evaluator_leaf_node_fail():
    rule = {"field": "score", "operator": ">=", "value": 700}
    context = {"score": 600}
    passed, trace = RuleEvaluator.evaluate_rule(rule, context)
    assert passed is False

def test_rule_evaluator_logical_and_pass():
    rule = {
        "condition": "AND",
        "rules": [
            {"field": "score", "operator": ">=", "value": 700},
            {"field": "amount", "operator": "<", "value": 1000}
        ]
    }
    context = {"score": 750, "amount": 500}
    passed, trace = RuleEvaluator.evaluate_rule(rule, context)
    assert passed is True

def test_rule_evaluator_logical_and_fail():
    rule = {
        "condition": "AND",
        "rules": [
            {"field": "score", "operator": ">=", "value": 700},
            {"field": "amount", "operator": "<", "value": 1000}
        ]
    }
    context = {"score": 750, "amount": 5000} # This fails the second rule
    passed, trace = RuleEvaluator.evaluate_rule(rule, context)
    assert passed is False

# -- Tests: API and Workflow Flow --
def test_workflow_evaluation_happy_path():
    """Test a full request that should get APPROVED."""
    payload = {
        "workflow_name": "loan_approval",
        "payload": {
            "credit_score": 750,
            "amount": 20000
        }
    }
    # For idempotency test later
    headers = {"idempotency-key": "req-123-happy"}
    
    response = client.post("/api/v1/workflow/evaluate", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "COMPLETED"
    assert data["current_stage"] == "APPROVED"
    assert "request_id" in data

def test_workflow_evaluation_reject_path():
    """Test a request that should get REJECTED."""
    payload = {
        "workflow_name": "loan_approval",
        "payload": {
            "credit_score": 600, # Fails PENDING rules -> NEEDS_REVIEW
            "amount": 50000      # Fails NEEDS_REVIEW rules -> REJECTED
        }
    }
    
    response = client.post("/api/v1/workflow/evaluate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "COMPLETED"
    assert data["current_stage"] == "REJECTED"

def test_idempotency_prevents_duplicate_processing():
    """Send two identical requests with the same key. The second should return instantly."""
    payload = {
        "workflow_name": "loan_approval",
        "payload": {"credit_score": 750, "amount": 20000}
    }
    headers = {"idempotency-key": "test-idem-999"}
    
    # First call
    response1 = client.post("/api/v1/workflow/evaluate", json=payload, headers=headers)
    assert response1.status_code == 200
    data1 = response1.json()
    
    # Second call
    response2 = client.post("/api/v1/workflow/evaluate", json=payload, headers=headers)
    assert response2.status_code == 200
    data2 = response2.json()
    
    # Assert they are identically cached responses
    assert data1["request_id"] == data2["request_id"]

def test_audit_logs():
    """Verify state transitions are correctly logged."""
    payload = {
        "workflow_name": "loan_approval",
        "payload": {"credit_score": 800, "amount": 1000}
    }
    response = client.post("/api/v1/workflow/evaluate", json=payload)
    request_id = response.json()["request_id"]
    
    audit_response = client.get(f"/api/v1/workflow/{request_id}/audit")
    assert audit_response.status_code == 200
    logs = audit_response.json()
    
    assert len(logs) > 0
    event_types = [log["event_type"] for log in logs]
    assert "WORKFLOW_STARTED" in event_types
    assert "RULE_EVALUATION" in event_types
    assert "STATE_TRANSITION" in event_types
