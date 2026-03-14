import uuid
import logging
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session
from app.models.repository import Repository
from app.engine.config_loader import WorkflowConfigLoader
from app.engine.rule_evaluator import RuleEvaluator
from app.services.external import SimulateExternalServices, ExternalServiceException

logger = logging.getLogger(__name__)

class WorkflowOrchestrator:
    """The central nervous system of the decision platform."""
    
    def __init__(self, db: Session):
        self.repo = Repository(db)

    async def execute(self, request_id: str, workflow_name: str, payload: Dict[str, Any], idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes a workflow evaluation.
        Handles idempotency, state persistence, rule evaluation, and audit logging.
        """
        
        # 1. Idempotency Check
        logger.info(f"[{request_id}] Intake started for workflow: {workflow_name}")
        if idempotency_key:
            created = self.repo.create_idempotency_record(request_id, idempotency_key)
            if not created:
                logger.info(f"[{request_id}] Found existing idempotency key {idempotency_key}. Returning cached response if complete.")
                record = self.repo.get_idempotency_record(idempotency_key)
                if record.status == "COMPLETED":
                    return record.response_payload
                else:
                    return {"status": "error", "message": "Request is currently processing concurrently."}

        # 2. State Initialization
        state = self.repo.get_state(request_id)
        if not state:
            state = self.repo.create_initial_state(request_id, workflow_name, payload)
            self.repo.log_audit_event(request_id, "WORKFLOW_STARTED", {"workflow": workflow_name, "initial_payload": payload})
            
        current_stage = state.current_stage

        # 3. Load Configuration
        try:
             config = WorkflowConfigLoader.get_workflow_config(workflow_name)
        except Exception as e:
             return self._fail_workflow(request_id, f"Configuration Error: {str(e)}", idempotency_key)
             
        stages = config.get("stages", {})

        # 4. Processing Loop (Process stages until a terminal stage is reached or rules require awaiting)
        loop_counter = 0
        max_loops = 10 # Prevent infinite loops in bad configs
        
        while loop_counter < max_loops:
            loop_counter += 1
            stage_def = stages.get(current_stage)
            
            if not stage_def:
                logger.error(f"[{request_id}] Stage {current_stage} not found in config.")
                return self._fail_workflow(request_id, f"Invalid state reference: {current_stage}", idempotency_key)

            # Check if Terminal
            if stage_def.get("is_terminal", False):
                logger.info(f"[{request_id}] Reached terminal stage: {current_stage}")
                response = {
                    "request_id": request_id,
                    "workflow_name": workflow_name,
                    "current_stage": current_stage,
                    "status": "COMPLETED",
                    "message": f"Workflow finished at state {current_stage}"
                }
                if idempotency_key:
                    self.repo.complete_idempotency_record(idempotency_key, response)
                return response

            # 5. External Data Enrichment (Simulated, if needed for complex rules)
            # In a real app, config would define "requires_enrichment: true" for specific stages
            if loop_counter == 1: # Only fetch once on initial run for simplicity
                try:
                    enriched_data = await SimulateExternalServices.fetch_enrichment_data(payload)
                    self.repo.update_state(request_id, current_stage, enriched_data)
                    self.repo.log_audit_event(request_id, "EXTERNAL_CALL_SUCCESS", {"enriched_data": enriched_data})
                    
                    # Merge payload and enriched data into a unified context for rule engine
                    context = payload.copy()
                    context.update(enriched_data)
                except ExternalServiceException as e:
                    self.repo.log_audit_event(request_id, "EXTERNAL_CALL_FAILURE", {"error": str(e)})
                    return self._fail_workflow(request_id, f"Dependency failure after retries: {str(e)}", idempotency_key)
            else:
                context = payload.copy()
                context.update(state.enriched_data)


            # 6. Evaluate Rules for the current stage
            ruleset = stage_def.get("rules", [])
            logger.info(f"[{request_id}] Evaluating rules for stage: {current_stage}")
            
            passed, trace = RuleEvaluator.evaluate_stage_rules(ruleset, context)
            
            self.repo.log_audit_event(
                request_id, 
                "RULE_EVALUATION", 
                {"stage": current_stage, "ruleset": ruleset, "passed": passed, "trace": trace}
            )

            # 7. Determine Next State
            next_stage = stage_def.get("on_success") if passed else stage_def.get("on_failure")
            
            if not next_stage:
                logger.error(f"[{request_id}] Config error: missing transition definition for stage {current_stage}")
                return self._fail_workflow(request_id, "Config error: missing transition definition", idempotency_key)
                
            logger.info(f"[{request_id}] Rules {'PASS' if passed else 'FAIL'}. Transitioning {current_stage} -> {next_stage}")
            self.repo.log_audit_event(request_id, "STATE_TRANSITION", {"from": current_stage, "to": next_stage, "reason": "rules_passed" if passed else "rules_failed"})
            
            self.repo.update_state(request_id, next_stage)
            current_stage = next_stage
            
        return self._fail_workflow(request_id, "Infinite loop detected in workflow execution", idempotency_key)


    def _fail_workflow(self, request_id: str, error_message: str, idempotency_key: str = None) -> Dict[str, Any]:
         logger.error(f"[{request_id}] Workflow failed: {error_message}")
         self.repo.update_state(request_id, "FAILED")
         self.repo.log_audit_event(request_id, "WORKFLOW_FAILED", {"error": error_message})
         response = {
             "request_id": request_id, 
             "status": "FAILED", 
             "message": error_message
         }
         if idempotency_key:
             self.repo.complete_idempotency_record(idempotency_key, response)
         return response
