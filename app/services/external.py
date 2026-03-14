import random
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import logging

logger = logging.getLogger(__name__)

class ExternalServiceException(Exception):
    pass

class SimulateExternalServices:
    """
    Simulates external dependencies like calling a credit bureau or fraud checker.
    Used to demonstrate failure handling, retries, and resilience.
    """

    @classmethod
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(ExternalServiceException),
        reraise=True
    )
    async def fetch_enrichment_data(cls, payload: dict) -> dict:
        """
        Simulates an API call. 
        Randomly fails to demonstrate tenacity taking over and retrying.
        """
        logger.info("Attempting to call external enrichment service...")
        
        # Simulate network delay
        await asyncio.sleep(0.5)

        # 30% chance of failure to test retries
        if random.random() < 0.3:
            logger.error("External service failed! Simulating 503 Service Unavailable.")
            raise ExternalServiceException("503 Service Unavailable")

        logger.info("External service call succeeded.")
        
        # Return some mock enriched data
        return {
            "internal_fraud_score": random.randint(1, 100),
            "bureau_status": "CLEAR"
        }
