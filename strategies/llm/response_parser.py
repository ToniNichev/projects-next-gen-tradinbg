"""
Response Parser Module

Parses LLM responses and extracts structured trading signals.
"""

import json
import logging
import re
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class ResponseParser:
    """Parse LLM responses to extract structured data"""
    
    def __init__(self, require_patterns: bool = False,
                 stop_loss_pct: float = 0.025,
                 take_profit_pct: float = 0.04,
                 min_position_size: float = 0.15,
                 max_position_size: float = 0.35):
        """
        Initialize response parser
        
        Args:
            require_patterns: Whether to require patterns in response
            stop_loss_pct: Default stop loss percentage
            take_profit_pct: Default take profit percentage
            min_position_size: Minimum position size
            max_position_size: Maximum position size
        """
        self.require_patterns = require_patterns
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.min_position_size = min_position_size
        self.max_position_size = max_position_size
    
    def parse(self, llm_output: str, current_price: float) -> Dict:
        """
        Parse LLM response to extract structured data.
        
        Handles both JSON and natural language responses.
        
        Args:
            llm_output: Raw text output from LLM
            current_price: Current market price
            
        Returns:
            Dict with parsed analysis data
        """
        # Try to extract JSON from response
        parsed_json = self._extract_json(llm_output)
        
        if parsed_json:
            return self._parse_json_response(parsed_json, current_price)
        else:
            # Fallback: Parse natural language response
            logger.warning("No valid JSON found, parsing natural language")
            return self._parse_natural_language(llm_output, current_price)
    
    def _extract_json(self, llm_output: str) -> Optional[Dict]:
        """
        Extract JSON from LLM output
        
        Args:
            llm_output: Raw LLM output text
            
        Returns:
            Parsed JSON dict, or None if not found
        """
        # Find all potential JSON blocks (including nested braces)
        json_pattern = r'\{(?:[^{}]|(?:\{[^{}]*\}))*\}'
        json_matches = re.findall(json_pattern, llm_output, re.DOTALL)
        
        # Find the first match that contains "direction" key
        for match in json_matches:
            if '"direction"' in match:
                try:
                    return json.loads(match)
                except json.JSONDecodeError:
                    continue
        
        return None
    
    def _parse_json_response(self, data: Dict, current_price: float) -> Dict:
        """
        Parse structured JSON response from LLM
        
        Args:
            data: Parsed JSON dict
            current_price: Current market price
            
        Returns:
            Normalized analysis dict
        """
        # Validate and normalize direction
        direction = data.get("direction", "neutral").lower()
        if direction not in ["bullish", "bearish", "neutral"]:
            direction = "neutral"
        
        # Validate confidence (0.0-1.0)
        confidence = float(data.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))
        
        # Extract text fields
        reasoning = data.get("reasoning", "LLM analysis completed")
        patterns_found = data.get("patterns_found", [])
        
        # Extract risk management parameters
        stop_loss_pct = float(data.get("stop_loss_pct", self.stop_loss_pct))
        take_profit_pct = float(data.get("take_profit_pct", self.take_profit_pct))
        position_size = float(data.get("position_size", 0.25))
        position_size = max(self.min_position_size, min(self.max_position_size, position_size))
        
        # Calculate absolute stop/target prices
        if direction == "bullish":
            stop_loss = current_price * (1 - stop_loss_pct)
            take_profit = current_price * (1 + take_profit_pct)
        elif direction == "bearish":
            stop_loss = current_price * (1 + stop_loss_pct)
            take_profit = current_price * (1 - take_profit_pct)
        else:
            stop_loss = 0.0
            take_profit = 0.0
        
        # If require_patterns is True and no patterns found, reduce confidence
        if self.require_patterns and not patterns_found:
            logger.warning(
                f"require_patterns=True but no patterns found. "
                f"LLM provided {direction} signal with {confidence:.1%} confidence but no specific patterns."
            )
            confidence = confidence * 0.5
        
        return {
            "direction": direction,
            "confidence": confidence,
            "reasoning": reasoning,
            "patterns_found": json.dumps(patterns_found),
            "suggested_stop_loss": stop_loss,
            "suggested_take_profit": take_profit,
            "suggested_position_size": position_size,
            "current_price": current_price,
            # Include percentages for recalculation in backtest mode
            "stop_loss_pct": stop_loss_pct,
            "take_profit_pct": take_profit_pct,
        }
    
    def _parse_natural_language(self, llm_output: str, current_price: float) -> Dict:
        """
        Parse natural language response (fallback)
        
        Args:
            llm_output: Raw LLM output text
            current_price: Current market price
            
        Returns:
            Basic analysis dict parsed from natural language
        """
        direction = "neutral"
        confidence = 0.3
        
        llm_lower = llm_output.lower()
        if "buy" in llm_lower or "bullish" in llm_lower or "long" in llm_lower:
            direction = "bullish"
            confidence = 0.5
        elif "sell" in llm_lower or "bearish" in llm_lower or "short" in llm_lower:
            direction = "bearish"
            confidence = 0.5
        
        # If require_patterns is True, warn about lack of structured patterns
        if self.require_patterns:
            logger.warning(
                "require_patterns=True but LLM response was not parseable JSON. "
                "Falling back to natural language parsing."
            )
            confidence = confidence * 0.3
        
        return {
            "direction": direction,
            "confidence": confidence,
            "reasoning": llm_output[:500],  # First 500 chars
            "patterns_found": "[]",
            "suggested_stop_loss": (
                current_price * (1 - self.stop_loss_pct) if direction == "bullish"
                else current_price * (1 + self.stop_loss_pct)
            ),
            "suggested_take_profit": (
                current_price * (1 + self.take_profit_pct) if direction == "bullish"
                else current_price * (1 - self.take_profit_pct)
            ),
            "suggested_position_size": 0.2,
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "current_price": current_price,
        }
