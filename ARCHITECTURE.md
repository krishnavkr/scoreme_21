# Architecture & System Design

## 1. System Overview
The Configurable Workflow Decision Platform acts as a central brain for processing business requests. It is designed to be domain-agnostic; meaning the engine doesn't inherently "know" what a Loan Application or an HR Onboarding request is. It only understands:
1.  **Incoming Schemas**: What data should look like.
2.  **Rules**: Logical conditions to evaluate against that data.
3.  **Workflows**: A sequence of stages to progress through.

## 2. Component Architecture

### 2.1 API Layer (FastAPI)
- **Role**: Ingress for all requests and egress for lookup/explainability.
- **Responsibilities**:
  - Accept HTTP POST requests for new evaluations.
  - Perform initial schema validation (via Pydantic).
  - Check for Idempotency keys in headers to prevent duplicate processing.
  - Return immediate synchronous responses or job IDs for asynchronous tracking (though for this assignment, we mostly execute synchronously for simplicity, but the design supports both).

### 2.2 Rule Engine (`app.engine.rule_evaluator`)
- **Role**: The logic processor.
- **Responsibilities**:
  - Takes a dictionary of contextual data (the incoming request payload + any augmented data).
  - Parses JSON-defined rules (e.g., `{"field": "credit_score", "operator": ">=", "value": 700}`).
  - Supports logical groupings (`AND`, `OR`).
  - Returns a boolean result and a detailed "trace" indicating exactly which conditions passed or failed.

### 2.3 Workflow Orchestrator (`app.engine.orchestrator`)
- **Role**: The conductor.
- **Responsibilities**:
  - Loads the specific workflow configuration for the request type.
  - Determines the current stage.
  - Invokes the Rule Engine.
  - Depending on the rule outcome, transitions the request to the next stage (e.g., `APPROVED`, `REJECTED`, `MANUAL_REVIEW`).
  - Triggers side-effects (like calling external services).

### 2.4 State & Data Management (SQLite / SQLAlchemy)
- **Role**: Persistence layer.
- **Models**:
  - `RequestState`: Stores the current stage of a workflow, the raw payload, and metadata.
  - `AuditLog`: An append-only table recording every state transition, rule evaluation trace, and system event.
  - `IdempotencyRecord`: Tracks uniquely processed requests to handle retries safely.

### 2.5 Resilient Services Layer (`app.services`)
- **Role**: Interaction with the outside world.
- **Responsibilities**:
  - Simulates an external API (e.g., a credit bureau check).
  - Wraps calls in `tenacity` retry blocks to handle transient network failures or simulated downtime.

## 3. Data Flow Example: Application Approval Workflow

1.  **Intake**: Client sends `POST /api/v1/workflow/loan_approval` with payload `{"amount": 5000, "credit_score": 750}` and `Idempotency-Key: req-123`.
2.  **Initial Validation**: FastAPI and Pydantic ensure required fields are present and typed correctly.
3.  **Idempotency Check**: System queries `IdempotencyRecord`. If `req-123` exists, returns the cached result immediately.
4.  **Orchestration Start**: Orchestrator loads `loan_approval.json` config. State set to `PENDING`. Log event.
5.  **External Enrichment (Simulated)**: Call external anti-fraud service. If it fails, retry 3 times.
6.  **Rule Evaluation**: Engine evaluates rules for `PENDING` stage.
    - Rule 1: `credit_score >= 700` (Pass)
    - Rule 2: `amount < 10000` (Pass)
7.  **State Transition**: Since rules passed, Workflow config dictates transition to `APPROVED`.
8.  **Final Commit**: Update `RequestState` to `APPROVED`. Insert trace into `AuditLog`. Mark `IdempotencyRecord` as complete.
9.  **Response**: Return 200 OK with the final state and decision explanation.

## 4. Key Trade-offs & Assumptions

- **Synchronous vs. Asynchronous execution**: For this hackathon, we assume workflows can be evaluated synchronously within the HTTP request lifecycle. A true enterprise system with long-running steps would use a message queue (e.g., RabbitMQ, Celery) to execute stages asynchronously. We designed the State models to support this future migration (a request can just sit in `PENDING` state while a background worker picks it up).
- **Database Choice**: We use built-in SQLite for portability and ease of testing/running during evaluation. The use of SQLAlchemy ORM allows seamless swapping to PostgreSQL in a production environment.
- **Configuration Format**: We use JSON for workflow configuration. While YAML is more human-readable, JSON is natively parsed faster and easier to validate programmatically with JSON Schema.

## 5. Defense of Modularity
The core engine is entirely decoupled from the business logic. If the business introduces a new requirement (e.g., "Flag any loan over $50k for manual review"), no Python code needs to change. An analyst simply updates the JSON configuration file to add that rule threshold to the `PENDING` stage rules. This fulfills the requirement for configurability without major code rewrites.
