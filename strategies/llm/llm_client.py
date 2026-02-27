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
            # Pass timeout to httpx client via kwargs
            self.client = ollama.Client(host=self.ollama_url, timeout=self.timeout_seconds)
            logger.info(f"Ollama client initialized: {self.ollama_url} (model: {self.model}, timeout: {self.timeout_seconds}s)")
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
        Send prompt to LLM and get analysis response with timeout protection
        
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
        import signal
        import threading
        
        start_time = datetime.utcnow()
        
        logger.info(f"Sending analysis request to Ollama ({self.model})...")
        
        # Set up signal-based timeout as a failsafe (Unix only, and only in main thread)
        def timeout_handler(signum, frame):
            raise TimeoutError(f"LLM request exceeded {self.timeout_seconds}s timeout")
        
        old_handler = None
        use_signal_timeout = False
        
        try:
            # Only use signal-based timeout if we're in the main thread
            # signal.signal() will raise ValueError if called from non-main thread
            is_main_thread = threading.current_thread() is threading.main_thread()
            
            if hasattr(signal, 'SIGALRM') and is_main_thread:
                use_signal_timeout = True
                old_handler = signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(self.timeout_seconds + 5)  # Add 5s buffer over ollama timeout
            
            # Call Ollama API (timeout configured in client initialization)
            response = self.client.generate(
                model=self.model,
                prompt=prompt,
                stream=False,
                options={
                    "temperature": self.temperature,
                    "num_predict": self.num_predict,
                }
            )
            
            # Cancel the alarm if we set it
            if use_signal_timeout:
                signal.alarm(0)
                if old_handler:
                    signal.signal(signal.SIGALRM, old_handler)
            
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
            
        except TimeoutError as e:
            # Cancel the alarm if we set it
            if use_signal_timeout:
                signal.alarm(0)
                if old_handler:
                    signal.signal(signal.SIGALRM, old_handler)
            
            logger.error(f"Ollama request timed out after {self.timeout_seconds}s")
            raise TimeoutError(f"Ollama timeout: {e}")
            
        except Exception as e:
            # Cancel the alarm on any error if we set it
            if use_signal_timeout:
                signal.alarm(0)
                if old_handler:
                    signal.signal(signal.SIGALRM, old_handler)
            
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
    
    def test_connection(self, quick: bool = False) -> bool:
        """
        Test connection to Ollama server and verify model availability
        
        Args:
            quick: If True, only check server reachability and model availability.
                   If False, also test model generation (slower but more thorough).
        
        Returns:
            True if connection successful and model available, False otherwise
        """
        try:
            # First, check if server is reachable by listing models
            # Use a temporary client with shorter timeout for the connection test
            import httpx
            test_client = self.ollama.Client(
                host=self.ollama_url,
                timeout=httpx.Timeout(10.0, connect=5.0)  # 10s total, 5s connect
            )
            
            response = test_client.list()
            
            # Handle both dict (older versions) and Pydantic object (newer versions)
            if hasattr(response, 'models'):
                models_list = response.models
                num_models = len(models_list)
                model_names = [getattr(m, 'model', str(m)) for m in models_list]
            elif isinstance(response, dict):
                models_list = response.get('models', [])
                num_models = len(models_list)
                model_names = [m.get('name', m.get('model', '')) for m in models_list]
            else:
                logger.warning(f"Unexpected response type from ollama.list(): {type(response)}")
                model_names = []
                num_models = 0
            
            logger.info(f"Ollama server is reachable, found {num_models} models")
            
            # Check if our model is available (handle both "model" and "model:latest" naming)
            model_base = self.model.split(':')[0] if ':' in self.model else self.model
            model_found = any(
                model_base in name or self.model in name 
                for name in model_names
            )
            
            if not model_found:
                logger.warning(f"Model '{self.model}' not found. Available models: {model_names}")
                logger.warning(f"You may need to run: ollama pull {self.model}")
                return False
            
            # If quick mode, skip the generation test
            if quick:
                logger.info(f"✓ Ollama server reachable and model '{self.model}' available")
                return True
            
            # Try a minimal generation request (may be slow if model not loaded)
            logger.info(f"Testing model '{self.model}' with a simple prompt (may take a moment)...")
            test_client.generate(
                model=self.model,
                prompt="ok",
                stream=False,
                options={"num_predict": 1}
            )
            logger.info(f"✓ Ollama connection test passed for model '{self.model}'")
            return True
        except Exception as e:
            logger.error(f"Ollama connection test failed: {e}")
            logger.error("Make sure Ollama is running: ollama serve")
            return False
