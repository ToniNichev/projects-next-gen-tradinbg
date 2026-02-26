#!/usr/bin/env python3
"""
Debug LLM Response - See EXACTLY what LLM returns

This bypasses all the strategy logic and directly calls the LLM
to show you the raw response.
"""

import logging
logging.basicConfig(level=logging.INFO, format="%(message)s")

def debug_llm_raw():
    """Call LLM directly and show raw response"""
    
    print("=" * 80)
    print("RAW LLM RESPONSE DEBUGGER")
    print("=" * 80)
    
    try:
        import ccxt
        from config import BotConfig
        from strategies.llm.market_data import MarketDataFetcher
        from strategies.llm.prompt_builder import PromptBuilder
        from strategies.llm.llm_client import OllamaClient
        from strategies.llm.response_parser import ResponseParser
        
        print("\n1. Fetching market data...")
        config = BotConfig.load()
        exchange = ccxt.binanceus({"enableRateLimit": True})
        candles = exchange.fetch_ohlcv("BTC/USDT", "1h", limit=100)
        
        print(f"   ✓ Got {len(candles)} candles")
        print(f"   ✓ Current price: ${candles[-1][4]:.2f}")
        
        print("\n2. Processing market data...")
        market_data = MarketDataFetcher.fetch_market_data(
            exchange=exchange,
            symbol="BTC/USDT",
            timeframe="1h",
            candle_data=candles
        )
        
        print(f"   ✓ RSI: {market_data['rsi']:.1f}")
        print(f"   ✓ MACD: {market_data['macd_histogram']:.2f}")
        print(f"   ✓ Trend: {market_data['trend']}")
        
        print("\n3. Building prompt...")
        prompt = PromptBuilder.create_market_analysis_prompt(
            market_data=market_data,
            trade_context=None,
            symbol="BTC/USDT"
        )
        
        print(f"   ✓ Prompt length: {len(prompt)} characters")
        print("\n   First 500 chars of prompt:")
        print("   " + "-" * 76)
        print("   " + prompt[:500].replace("\n", "\n   "))
        print("   " + "-" * 76)
        
        print("\n4. Calling LLM...")
        print(f"   Model: {config.llm_ollama_model}")
        print(f"   URL: {config.llm_ollama_url}")
        print(f"   Temperature: {config.llm_temperature}")
        print(f"   Timeout: {config.llm_timeout_seconds}s")
        print("\n   Waiting for response (may take 20-30 seconds)...\n")
        
        llm_client = OllamaClient(
            ollama_url=config.llm_ollama_url,
            model=config.llm_ollama_model,
            temperature=config.llm_temperature,
            num_predict=config.llm_num_predict,
            timeout_seconds=config.llm_timeout_seconds
        )
        
        response = llm_client.analyze(prompt)
        
        print("=" * 80)
        print("5. RAW LLM RESPONSE")
        print("=" * 80)
        print(response["response"])
        print("=" * 80)
        print(f"\nResponse time: {response['duration_ms']}ms")
        
        print("\n6. Parsing response...")
        parser = ResponseParser(
            require_patterns=False,
            stop_loss_pct=config.stop_loss_pct,
            take_profit_pct=config.take_profit_pct,
            min_position_size=config.min_position_size,
            max_position_size=config.max_position_size
        )
        
        current_price = candles[-1][4]
        parsed = parser.parse(response["response"], current_price)
        
        print("\n" + "=" * 80)
        print("PARSED RESULT")
        print("=" * 80)
        print(f"Direction:  {parsed['direction'].upper()}")
        print(f"Confidence: {parsed['confidence']:.1%}")
        print(f"Position:   {parsed['suggested_position_size']:.1%}")
        print(f"\nReasoning:")
        print(parsed.get('reasoning', 'No reasoning')[:300])
        
        if 'patterns_found' in parsed:
            import json
            try:
                patterns = json.loads(parsed['patterns_found'])
                if patterns:
                    print(f"\nPatterns:")
                    for p in patterns:
                        print(f"  - {p}")
            except:
                pass
        
        print("\n" + "=" * 80)
        print("DIAGNOSIS")
        print("=" * 80)
        
        if parsed['direction'] == 'neutral':
            print("❌ LLM returned NEUTRAL")
            print("\nPossible reasons:")
            
            # Check if JSON was found
            if '"direction"' not in response["response"]:
                print("  ⚠️  No JSON found in response!")
                print("     → LLM didn't follow JSON format")
                print("     → Try different model (mistral)")
                print("     → Or adjust prompt")
            
            # Check reasoning
            reasoning_lower = response["response"].lower()
            if "neutral" in reasoning_lower:
                print("  ⚠️  LLM explicitly chose neutral")
                print("     → Market signals genuinely mixed")
                print("     → Try different timeframe/symbol")
            
            if "unclear" in reasoning_lower or "mixed" in reasoning_lower:
                print("  ⚠️  LLM sees conflicting signals")
                print("     → Current market conditions unclear")
                print("     → Try trending market instead")
        
        else:
            print(f"✅ LLM returned {parsed['direction'].upper()}")
            print(f"   Confidence: {parsed['confidence']:.1%}")
            
            if parsed['confidence'] < 0.3:
                print(f"\n⚠️  But confidence is low ({parsed['confidence']:.1%})")
                print("   → Would be filtered by default threshold (30%)")
                print("   → Lower min_signal_confidence to 0.2")
            else:
                print("\n✅ Signal would PASS filters!")
                print("   → Should generate trades in backtest")
        
        print("=" * 80)
        
        return parsed['direction'] != 'neutral'
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        
        print("\n" + "=" * 80)
        print("ERROR DIAGNOSIS")
        print("=" * 80)
        
        error_str = str(e).lower()
        
        if "connection" in error_str:
            print("Connection error - Ollama not running")
            print("\nFix:")
            print("  1. Check: ps aux | grep ollama")
            print("  2. Start: ollama serve")
        
        elif "timeout" in error_str:
            print("Timeout - LLM taking too long")
            print("\nFix:")
            print("  1. Increase timeout: llm_timeout_seconds=90")
            print("  2. Use faster model: llm_ollama_model='phi3'")
        
        elif "not enough candles" in error_str:
            print("Insufficient data")
            print("\nFix:")
            print("  1. Increase days: --days 7")
        
        else:
            print("Unknown error - see traceback above")
        
        return False


if __name__ == "__main__":
    debug_llm_raw()
