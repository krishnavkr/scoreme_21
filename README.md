# Configurable Workflow Decision Platform

## Overview
This is a resilient, configurable workflow decision engine built in Python. It evaluates business rules against structured incoming requests, executes workflow stages based on the evaluation, maintains state, handles errors gracefully with retries, and maintains a complete audit trail.

The core principle of this system is **configurability**: business logic (rules and workflow stages) is separated from code. It can be modified via configuration files (JSON/YAML) without rewriting the core engine.

## Key Features
- **Dynamic Rule Engine**: Evaluate complex, nested logical rules using a configuration-driven approach.
- **Workflow Orchestration**: Define stages (e.g., PENDING, APPROVED, MANUAL_REVIEW) and transitions based on rule outcomes.
- **Idempotency**: Safely retry requests without processing duplicates or causing unintended side effects.
- **Auditability**: Every decision, rule evaluation, and state change is logged with rich context for explainability.
- **Resilience**: Simulated external dependencies are wrapped in robust retry logic (using exponentially backing off retries).
- **FastAPI REST Interface**: Easy-to-use API for submitting requests and querying state/audit logs.

## Quick Start (Local Development)

### 1. Requirements
- Python 3.10+
- SQLite (built-in)

### 2. Setup
```bash
# Clone the repository (if applicable)
# Create a virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Running the Server
```bash
uvicorn app.main:app --reload
```
The API documentation will be available at `http://localhost:8000/docs`.

### 4. Running Tests
```bash
pytest -v
```

## Structure
- `app/api`: FastAPI route handlers
- `app/engine`: Core logic for evaluating rules and orchestrating workflows
- `app/models`: Database and Schema definitions (SQLAlchemy & Pydantic)
- `app/services`: External integrations and resilience wrappers
- `config/`: JSON configuration files defining specific workflows (e.g., `loan_approval.json`)
- `tests/`: Pytest suite covering core engine, API, and edge cases.
