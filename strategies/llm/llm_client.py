"""
LLM Client Module

Handles communication with Ollama API for market analysis.
"""

import logging
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class OllamaClient:
    """Client for interacting with Ollama LLM API"""
    
    def __init__(self, ollama_url: str, model: str, temperature: float = 0.3, 
                 num_predict: int = 1000, timeout_seconds: int = 60):
        """
        Initialize Ollama client
        
        Args:
            ollama_url: Ollama server URL (e.g., "http://localhost:11434")
            model: Model name (e.g., "mistral")
            temperature: Sampling temperature (0.0-1.0, default: 0.3)
            num_predict: Max tokens to generate (default: 1000)
            timeout_seconds: Request timeout (default: 60)
        """
        self.ollama_url = ollama_url
        self.model = model
        self.temperature = temperature
        self.num_predict = num_predict
        self.timeout_seconds = timeout_seconds
        
        # Validate and normalize parameters
        self._validate_parameters()
        
        # Initialize Ollama client
        try:
            import ollama
            self.ollama = ollama
            self.client = ollama.Client(host=self.ollama_url)
            logger.info(f"Ollama client initialized: {self.ollama_url} (model: {self.model})")
        except ImportError:
            logger.error("ollama package not installed. Install with: pip install ollama")
            raise ImportError("ollama package required for LLM strategy")
    
    def _validate_parameters(self):
        """Validate and normalize LLM parameters"""
        # Validate temperature (0.0 - 1.0)
        if not 0.0 <= self.temperature <= 1.0:
            logger.warning(f"Invalid temperature {self.temperature}, using default 0.3")
            self.temperature = 0.3
        
        # Validate num_predict (minimum 300, maximum 2000)
        if self.num_predict < 300:
            logger.warning(f"num_predict {self.num_predict} too low, using 500")
            self.num_predict = 500
        elif self.num_predict > 2000:
            logger.warning(f"num_predict {self.num_predict} too high, using 2000")
            self.num_predict = 2000
        
        # Warn if temperature is high
        if self.temperature > 0.5:
            logger.warning(f"High temperature ({self.temperature}) may cause inconsistent analysis")
    
    def analyze(self, prompt: str) -> Dict:
        """
        Send prompt to LLM and get analysis response
        
        Args:
            prompt: Analysis prompt to send to LLM
            
        Returns:
            Dict with:
            - response: LLM text response
            - duration_ms: Analysis duration in milliseconds
            
        Raises:
            ConnectionError: If cannot connect to Ollama
            TimeoutError: If request times out
        """
        start_time = datetime.utcnow()
        
        logger.info(f"Sending analysis request to Ollama ({self.model})...")
        
        try:
            # Call Ollama API with timeout
            response = self.client.generate(
                model=self.model,
                prompt=prompt,
                stream=False,
                options={
                    "temperature": self.temperature,
                    "num_predict": self.num_predict,
                    "timeout": self.timeout_seconds,
                }
            )
            
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # Handle both dict (ollama <0.2.0) and Pydantic object (ollama >=0.2.0)
            if isinstance(response, dict):
                llm_output = response.get("response", "")
            else:
                llm_output = getattr(response, "response", "") or ""
            
            logger.info(f"LLM response received in {duration_ms}ms")
            logger.debug(f"LLM output: {llm_output[:500]}...")
            
            return {
                "response": llm_output,
                "duration_ms": duration_ms,
            }
            
        except Exception as e:
            err_str = str(e).lower()
            err_type = type(e).__name__

            # Normalize connection errors from httpx/ollama into ConnectionError
            if any(t in err_type for t in ("ConnectError", "ConnectTimeout", "ConnectionError")) or \
               any(s in err_str for s in ("connection refused", "connect call failed", "cannot connect")):
                logger.error(f"Cannot connect to Ollama at {self.ollama_url}. Is Ollama running? ({err_type}: {e})")
                raise ConnectionError(f"Ollama connection failed: {e}")

            # Normalize timeout errors
            if any(t in err_type for t in ("TimeoutError", "ReadTimeout", "WriteTimeout")) or \
               "timed out" in err_str or "timeout" in err_str:
                logger.error(f"Ollama request timed out after {self.timeout_seconds}s ({err_type}: {e})")
                raise TimeoutError(f"Ollama timeout: {e}")

            logger.error(f"Ollama API call failed ({err_type}): {e}")
            raise
    
    def test_connection(self) -> bool:
        """
        Test connection to Ollama server
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Try a simple generation request
            self.client.generate(
                model=self.model,
                prompt="test",
                stream=False,
                options={"num_predict": 1}
            )
            return True
        except Exception as e:
            logger.error(f"Ollama connection test failed: {e}")
            return False
