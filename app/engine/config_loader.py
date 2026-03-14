import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Base directory for the configuration files
CONFIG_DIR = Path(__file__).parent.parent.parent / "config"

class WorkflowConfigLoader:
    """Loads and caches workflow configurations from the filesystem."""
    
    _cache = {}

    @classmethod
    def get_workflow_config(cls, workflow_name: str) -> dict:
        """
        Loads a workflow configuration by name (e.g., 'loan_approval').
        In a production system, this might query a database or Redis cache.
        """
        if workflow_name in cls._cache:
            return cls._cache[workflow_name]

        config_path = CONFIG_DIR / f"{workflow_name}.json"
        
        if not config_path.exists():
            raise FileNotFoundError(f"Workflow configuration not found: {workflow_name}.json")

        try:
            with open(config_path, "r") as f:
                config = json.load(f)
                cls._cache[workflow_name] = config
                logger.info(f"Loaded workflow config: {workflow_name}")
                return config
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse config {workflow_name}: {str(e)}")
            raise ValueError(f"Invalid JSON in config {workflow_name}") from e
