import operator
from typing import Any, Dict, List, Optional
from loguru import logger # Optional if we use standard logging, but let's use standard logging for simplicity

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Map string operators from JSON to actual Python functions
OPERATORS = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    "<": operator.lt,
    ">=": operator.ge,
    "<=": operator.le,
    "IN": lambda x, y: x in y,
    "NOT_IN": lambda x, y: x not in y,
}

class RuleEvaluator:
    """Evaluates business rules against a contextual payload."""
    
    @classmethod
    def evaluate_rule(cls, rule: Dict[str, Any], context: Dict[str, Any]) -> tuple[bool, Dict[str, Any]]:
        """
        Evaluates a single rule (which could be a nested AND/OR condition).
        Returns:
            - Boolean indicating success/failure
            - Dictionary containing the trace (why it succeeded/failed)
        """
        condition = rule.get("condition")
        
        # Base case: Leaf node (a direct comparison rule)
        if not condition:
            return cls._evaluate_leaf_rule(rule, context)
            
        # Recursive case: Logical grouping (AND / OR)
        sub_rules = rule.get("rules", [])
        if not sub_rules:
            logger.warning(f"Empty logical group: {rule}")
            return True, {"condition": condition, "result": True, "reason": "empty_group"}

        trace_details = []
        
        if condition.upper() == "AND":
            for sub in sub_rules:
                passed, trace = cls.evaluate_rule(sub, context)
                trace_details.append(trace)
                if not passed:
                    return False, {"condition": "AND", "result": False, "break_early": True, "trace": trace_details}
            return True, {"condition": "AND", "result": True, "trace": trace_details}
            
        elif condition.upper() == "OR":
            for sub in sub_rules:
                passed, trace = cls.evaluate_rule(sub, context)
                trace_details.append(trace)
                if passed:
                    return True, {"condition": "OR", "result": True, "break_early": True, "trace": trace_details}
            return False, {"condition": "OR", "result": False, "trace": trace_details}
            
        else:
            raise ValueError(f"Unknown logical condition: {condition}")

    @classmethod
    def _evaluate_leaf_rule(cls, rule: Dict[str, Any], context: Dict[str, Any]) -> tuple[bool, Dict[str, Any]]:
        field = rule.get("field")
        op_str = rule.get("operator")
        expected_value = rule.get("value")
        
        if not field or not op_str:
            raise ValueError(f"Invalid leaf rule structure: {rule}")
            
        actual_value = context.get(field)
        
        # If the field doesn't exist in the context payload, the rule fails
        if actual_value is None:
             trace = {"rule": rule, "result": False, "actual_value": None, "reason": "field_missing"}
             logger.debug(f"Rule FAILED (Missing field): {trace}")
             return False, trace
            
        op_func = OPERATORS.get(op_str)
        if not op_func:
            raise ValueError(f"Unknown operator: {op_str}")
            
        try:
            passed = op_func(actual_value, expected_value)
            trace = {"rule": rule, "result": passed, "actual_value": actual_value}
            logger.debug(f"Rule Evaluated: {trace}")
            return passed, trace
        except Exception as e:
            trace = {"rule": rule, "result": False, "actual_value": actual_value, "error": str(e)}
            logger.error(f"Rule Evaluation ERROR: {trace}")
            return False, trace

    @classmethod
    def evaluate_stage_rules(cls, ruleset: List[Dict[str, Any]], context: Dict[str, Any]) -> tuple[bool, List[Dict]]:
        """
        Evaluates a list of top-level rules for a stage. 
        Implies an AND condition across all top-level rules.
        """
        if not ruleset:
            return True, [{"reason": "no_rules_defined", "result": True}]
            
        full_trace = []
        for rule in ruleset:
            passed, trace = cls.evaluate_rule(rule, context)
            full_trace.append(trace)
            if not passed:
                return False, full_trace
                
        return True, full_trace
