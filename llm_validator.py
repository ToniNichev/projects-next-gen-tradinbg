"""
LLM Direction Validator - Quick validation of LLM prediction accuracy.

This module provides fast validation testing for LLM trading strategies
without the overhead of full per-candle backtesting.

Usage:
    # CLI
    python3 llm_validator.py
    python3 llm_validator.py --tests 10 --model mistral
    
    # From code
    from llm_validator import LLMValidator
    validator = LLMValidator()
    results = validator.run_validation(num_tests=5)
    print(f"Accuracy: {results['accuracy']:.1%}")
"""

import argparse
import json
import logging
import re
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass

import ccxt

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of a single validation test"""
    test_date: datetime
    predicted_direction: str
    predicted_confidence: float
    actual_direction: str
    actual_change_pct: float
    is_correct: bool
    reasoning: str = ""


class LLMValidator:
    """
    Validates LLM prediction accuracy using historical data.
    
    Instead of slow per-candle backtesting, this runs quick validation tests:
    1. Take 7 days of historical data
    2. Ask LLM to predict next 24 hours
    3. Compare prediction to actual result
    4. Repeat for multiple time periods
    """
    
    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        model: str = "mistral",
        symbol: str = "BTC/USDT",
        timeframe: str = "1h",
    ):
        self.ollama_url = ollama_url
        self.model = model
        self.symbol = symbol
        self.timeframe = timeframe
        
        # Initialize exchange
        self.exchange = ccxt.binanceus({"enableRateLimit": True})
        
        # Initialize Ollama client
        if OLLAMA_AVAILABLE:
            self.ollama_client = ollama.Client(host=ollama_url)
        else:
            raise ImportError("ollama package required. Install with: pip install ollama")
    
    def run_validation(
        self,
        num_tests: int = 5,
        days_between_tests: int = 7,
        training_days: int = 7,
        prediction_hours: int = 24,
    ) -> Dict:
        """
        Run multiple validation tests across different time periods.
        
        Args:
            num_tests: Number of validation tests to run
            days_between_tests: Days between each test period
            training_days: Days of data to show LLM for each test
            prediction_hours: Hours ahead to predict
            
        Returns:
            Dictionary with validation results and accuracy metrics
        """
        logger.info("=" * 70)
        logger.info("LLM DIRECTION VALIDATION TEST")
        logger.info(f"Model: {self.model} | Symbol: {self.symbol}")
        logger.info(f"Tests: {num_tests} | Training: {training_days} days | Predict: {prediction_hours}h")
        logger.info("=" * 70)
        
        results: List[ValidationResult] = []
        
        for i in range(num_tests):
            days_ago = 8 + (i * days_between_tests)  # Start 8 days ago, then go back
            
            logger.info(f"\nTest {i+1}/{num_tests}")
            logger.info("-" * 50)
            
            try:
                result = self._run_single_test(
                    days_ago=days_ago,
                    training_days=training_days,
                    prediction_hours=prediction_hours,
                )
                results.append(result)
                
                status = "✓ CORRECT" if result.is_correct else "✗ WRONG"
                logger.info(f"Date: {result.test_date.date()}")
                logger.info(f"Predicted: {result.predicted_direction} ({result.predicted_confidence:.0%})")
                logger.info(f"Actual: {result.actual_direction} ({result.actual_change_pct:+.2f}%)")
                logger.info(f"Result: {status}")
                
            except Exception as e:
                logger.error(f"Test {i+1} failed: {e}")
                continue
        
        # Calculate summary metrics
        if not results:
            return {"error": "No tests completed successfully"}
        
        correct = sum(1 for r in results if r.is_correct)
        accuracy = correct / len(results)
        
        # Calculate accuracy by confidence level
        high_conf = [r for r in results if r.predicted_confidence >= 0.7]
        high_conf_correct = sum(1 for r in high_conf if r.is_correct)
        high_conf_accuracy = high_conf_correct / len(high_conf) if high_conf else 0
        
        summary = {
            "total_tests": len(results),
            "correct": correct,
            "wrong": len(results) - correct,
            "accuracy": accuracy,
            "high_confidence_tests": len(high_conf),
            "high_confidence_accuracy": high_conf_accuracy,
            "model": self.model,
            "symbol": self.symbol,
            "results": [
                {
                    "date": r.test_date.isoformat(),
                    "predicted": r.predicted_direction,
                    "confidence": r.predicted_confidence,
                    "actual": r.actual_direction,
                    "change_pct": r.actual_change_pct,
                    "correct": r.is_correct,
                }
                for r in results
            ],
        }
        
        # Print summary
        logger.info("\n" + "=" * 70)
        logger.info("VALIDATION SUMMARY")
        logger.info("=" * 70)
        logger.info(f"Total Tests: {summary['total_tests']}")
        logger.info(f"Correct: {summary['correct']} | Wrong: {summary['wrong']}")
        logger.info(f"Overall Accuracy: {summary['accuracy']:.1%}")
        if high_conf:
            logger.info(f"High Confidence (≥70%) Accuracy: {summary['high_confidence_accuracy']:.1%} ({len(high_conf)} tests)")
        logger.info(f"Baseline (random): 50%")
        logger.info(f"Edge over random: {(accuracy - 0.5) * 100:+.1f}%")
        logger.info("=" * 70)
        
        # Recommendation
        if accuracy >= 0.7:
            logger.info("✓ RECOMMENDATION: LLM shows strong predictive ability. Good for trading signals.")
        elif accuracy >= 0.6:
            logger.info("~ RECOMMENDATION: LLM shows moderate ability. Use as confirmation, not primary signal.")
        else:
            logger.info("✗ RECOMMENDATION: LLM accuracy is weak. Not recommended for trading decisions.")
        
        return summary
    
    def _run_single_test(
        self,
        days_ago: int,
        training_days: int,
        prediction_hours: int,
    ) -> ValidationResult:
        """Run a single validation test for a specific time period."""
        
        # Calculate required candles
        training_candles_needed = training_days * 24  # 1h candles
        validation_candles_needed = prediction_hours
        total_candles = training_candles_needed + validation_candles_needed + 10  # Buffer
        
        # Fetch historical data
        since = self.exchange.parse8601(
            (datetime.utcnow() - timedelta(days=days_ago + training_days + 2)).strftime("%Y-%m-%dT00:00:00Z")
        )
        candles = self.exchange.fetch_ohlcv(self.symbol, self.timeframe, since=since, limit=total_candles)
        
        if len(candles) < training_candles_needed + validation_candles_needed:
            raise ValueError(f"Not enough candles: got {len(candles)}, need {training_candles_needed + validation_candles_needed}")
        
        # Split into training and validation
        training_candles = candles[:training_candles_needed]
        validation_candles = candles[training_candles_needed:training_candles_needed + validation_candles_needed]
        
        test_date = datetime.utcfromtimestamp(training_candles[-1][0] / 1000)
        
        # Calculate actual result
        val_start_price = validation_candles[0][1]  # Open
        val_end_price = validation_candles[-1][4]   # Close
        actual_change = ((val_end_price - val_start_price) / val_start_price) * 100
        actual_direction = "BULLISH" if actual_change > 0 else "BEARISH"
        
        # Calculate technical indicators for prompt
        closes = np.array([c[4] for c in training_candles])
        highs = np.array([c[2] for c in training_candles])
        lows = np.array([c[3] for c in training_candles])
        
        rsi = self._calculate_rsi(closes)
        sma_20 = np.mean(closes[-20:])
        sma_50 = np.mean(closes[-50:]) if len(closes) >= 50 else sma_20
        current_price = closes[-1]
        price_change = ((closes[-1] - closes[0]) / closes[0]) * 100
        high_period = np.max(highs)
        low_period = np.min(lows)
        
        # Create prompt
        prompt = self._create_validation_prompt(
            current_price=current_price,
            price_change=price_change,
            rsi=rsi,
            sma_20=sma_20,
            sma_50=sma_50,
            high_period=high_period,
            low_period=low_period,
            training_days=training_days,
            prediction_hours=prediction_hours,
            recent_candles=training_candles[-5:],
        )
        
        # Call LLM
        response = self.ollama_client.generate(
            model=self.model,
            prompt=prompt,
            stream=False,
            options={"temperature": 0.3, "num_predict": 500},
        )
        
        llm_output = response.get("response", "")
        
        # Parse response
        predicted_direction, confidence, reasoning = self._parse_llm_response(llm_output)
        
        return ValidationResult(
            test_date=test_date,
            predicted_direction=predicted_direction,
            predicted_confidence=confidence,
            actual_direction=actual_direction,
            actual_change_pct=actual_change,
            is_correct=(predicted_direction == actual_direction),
            reasoning=reasoning,
        )
    
    def _calculate_rsi(self, closes: np.ndarray, period: int = 14) -> float:
        """Calculate RSI indicator."""
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-period:]) if len(gains) >= period else np.mean(gains)
        avg_loss = np.mean(losses[-period:]) if len(losses) >= period else np.mean(losses)
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    def _create_validation_prompt(
        self,
        current_price: float,
        price_change: float,
        rsi: float,
        sma_20: float,
        sma_50: float,
        high_period: float,
        low_period: float,
        training_days: int,
        prediction_hours: int,
        recent_candles: list,
    ) -> str:
        """Create the prompt for LLM prediction."""
        
        trend = "Bullish (SMA20 > SMA50)" if sma_20 > sma_50 else "Bearish (SMA20 < SMA50)"
        
        # Format recent candles
        candle_summary = ""
        for c in recent_candles:
            t = datetime.utcfromtimestamp(c[0] / 1000)
            change = ((c[4] - c[1]) / c[1]) * 100
            candle_summary += f"  {t}: Open ${c[1]:,.2f}, Close ${c[4]:,.2f}, Change: {change:+.2f}%\n"
        
        return f"""You are an expert cryptocurrency trader making a BINARY prediction. Based on {training_days}-day market data for {self.symbol}, you MUST predict if the price will be HIGHER or LOWER in {prediction_hours} hours.

=== MARKET DATA ===
Current Price: ${current_price:,.2f}
{training_days}-Day High: ${high_period:,.2f}
{training_days}-Day Low: ${low_period:,.2f}
{training_days}-Day Price Change: {price_change:+.2f}%

=== INDICATORS ===
RSI (14): {rsi:.1f} {"(Oversold - potential bounce)" if rsi < 30 else "(Overbought - potential drop)" if rsi > 70 else ""}
SMA 20 vs SMA 50: {"Bullish (SMA20 > SMA50)" if sma_20 > sma_50 else "Bearish (SMA20 < SMA50)"}
Distance from High: {((current_price - high_period) / high_period * 100):.1f}%
Distance from Low: {((current_price - low_period) / low_period * 100):.1f}%

=== RECENT CANDLES ===
{candle_summary}
=== REQUIRED RESPONSE ===
You MUST choose either "bullish" (price goes UP) or "bearish" (price goes DOWN).
Do NOT say "neutral" or "uncertain" - you must commit to a direction.

Respond with ONLY this JSON:
{{"direction": "bullish" or "bearish", "confidence": 0.5 to 1.0, "reasoning": "one sentence"}}
"""
    
    def _parse_llm_response(self, llm_output: str) -> tuple:
        """Parse LLM response to extract direction and confidence."""
        
        # Try to find JSON
        json_match = re.search(r'\{[^{}]*"direction"[^{}]*\}', llm_output, re.DOTALL)
        
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                direction = data.get("direction", "unknown").upper()
                confidence = float(data.get("confidence", 0.5))
                confidence = max(0.0, min(1.0, confidence))
                reasoning = data.get("reasoning", "")
                
                # Convert neutral/unknown to a direction based on context
                if direction in ("NEUTRAL", "UNKNOWN", "SIDEWAYS"):
                    # If LLM is indecisive, analyze the reasoning
                    reason_lower = reasoning.lower()
                    if any(w in reason_lower for w in ["up", "rise", "gain", "bullish", "bounce"]):
                        direction = "BULLISH"
                        confidence = max(0.5, confidence - 0.1)  # Lower confidence for inferred
                    elif any(w in reason_lower for w in ["down", "fall", "drop", "bearish", "decline"]):
                        direction = "BEARISH"
                        confidence = max(0.5, confidence - 0.1)
                    else:
                        # Default to a coin flip direction with low confidence
                        direction = "BULLISH"  # We'll count this as wrong usually
                        confidence = 0.5
                
                return direction, confidence, reasoning
            except (json.JSONDecodeError, ValueError):
                pass
        
        # Fallback: keyword matching in full output
        llm_lower = llm_output.lower()
        
        # Count bullish vs bearish keywords
        bullish_words = ["bullish", "buy", "long", "upward", "rise", "increase", "gain", "higher"]
        bearish_words = ["bearish", "sell", "short", "downward", "fall", "decrease", "drop", "lower"]
        
        bullish_score = sum(1 for w in bullish_words if w in llm_lower)
        bearish_score = sum(1 for w in bearish_words if w in llm_lower)
        
        if bullish_score > bearish_score:
            direction = "BULLISH"
        elif bearish_score > bullish_score:
            direction = "BEARISH"
        else:
            direction = "BULLISH"  # Default
        
        return direction, 0.5, llm_output[:200]
    
    def quick_test(self) -> Dict:
        """
        Run a quick single-period test (fastest validation).
        
        Returns prediction for next 24h based on last 7 days.
        """
        logger.info("Running quick validation test...")
        
        result = self._run_single_test(
            days_ago=1,  # Test against yesterday
            training_days=7,
            prediction_hours=24,
        )
        
        return {
            "test_date": result.test_date.isoformat(),
            "predicted_direction": result.predicted_direction,
            "predicted_confidence": result.predicted_confidence,
            "actual_direction": result.actual_direction,
            "actual_change_pct": result.actual_change_pct,
            "is_correct": result.is_correct,
            "reasoning": result.reasoning,
        }


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Validate LLM trading prediction accuracy")
    parser.add_argument("--tests", type=int, default=5, help="Number of validation tests")
    parser.add_argument("--model", type=str, default="mistral", help="Ollama model to use")
    parser.add_argument("--symbol", type=str, default="BTC/USDT", help="Trading symbol")
    parser.add_argument("--quick", action="store_true", help="Run quick single test")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    
    args = parser.parse_args()
    
    try:
        validator = LLMValidator(model=args.model, symbol=args.symbol)
        
        if args.quick:
            results = validator.quick_test()
        else:
            results = validator.run_validation(num_tests=args.tests)
        
        if args.json:
            print(json.dumps(results, indent=2))
            
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        raise


if __name__ == "__main__":
    main()
