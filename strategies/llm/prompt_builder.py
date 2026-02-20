"""
Prompt Builder Module

Constructs prompts for LLM market analysis.
"""

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class PromptBuilder:
    """Build prompts for LLM analysis"""
    
    @staticmethod
    def create_market_analysis_prompt(
        market_data: Dict,
        trade_context: Optional[Dict],
        symbol: str
    ) -> str:
        """
        Create prompt for LLM market analysis
        
        Args:
            market_data: Dict with current market data and indicators
            trade_context: Optional dict with historical trade context
            symbol: Trading pair symbol
            
        Returns:
            Formatted prompt string for LLM
        """
        # Format support/resistance levels
        support_str = ', '.join([
            f'${s:.0f}' for s in market_data['support_levels']
        ]) if market_data['support_levels'] else "None identified"
        
        resistance_str = ', '.join([
            f'${r:.0f}' for r in market_data['resistance_levels']
        ]) if market_data['resistance_levels'] else "None identified"
        
        # Format recent candles
        candle_summary = "\n".join([
            f"  {c['timestamp'][:10]}: Open ${c['open']:.2f}, High ${c['high']:.2f}, "
            f"Low ${c['low']:.2f}, Close ${c['close']:.2f}, Change: {c['change_pct']:+.2f}%"
            for c in market_data['recent_candles'][-5:]  # Last 5 candles
        ])
        
        # Build base prompt with market data
        prompt = f"""You are an expert cryptocurrency technical analyst. Analyze the current market data and provide a trading recommendation.

SYMBOL: {symbol}
CURRENT PRICE: ${market_data['current_price']:.2f}
TIMEFRAME: {market_data['timeframe']}

=== TECHNICAL INDICATORS ===
- RSI (14): {market_data['rsi']:.1f} {'(Oversold)' if market_data['rsi'] < 30 else '(Overbought)' if market_data['rsi'] > 70 else '(Neutral)'}
- MACD Line: {market_data['macd_line']:.2f}
- MACD Signal: {market_data['macd_signal']:.2f}
- MACD Histogram: {market_data['macd_histogram']:.2f} {'(Bullish crossover)' if market_data['macd_histogram'] > 0 else '(Bearish crossover)'}
- SMA 20: ${market_data['sma_20']:.2f}
- SMA 50: ${market_data['sma_50']:.2f}
- Trend: {market_data['trend'].upper()}

=== VOLUME ANALYSIS ===
- Current Volume Ratio: {market_data['volume_ratio']:.2f}x average {'(High volume)' if market_data['volume_ratio'] > 1.5 else '(Above average)' if market_data['volume_ratio'] > 1.0 else '(Below average)'}

=== SUPPORT & RESISTANCE ===
- Support Levels: {support_str}
- Resistance Levels: {resistance_str}

=== PRICE ACTION ===
- 24h Change: {market_data['price_change_24h']:+.2f}%
- 7d Change: {market_data['price_change_7d']:+.2f}%

RECENT CANDLES (Last 5):
{candle_summary}
"""
        
        # Add trade context if available
        if trade_context and trade_context['total_trades'] > 0:
            prompt += PromptBuilder._format_trade_context(trade_context)
        
        # Add analysis instructions
        prompt += """
=== ANALYSIS TASK ===
Based on the technical indicators, price action, and market conditions above, provide a trading recommendation:

1. What chart patterns or signals do you see?
2. Is the momentum bullish, bearish, or neutral?
3. Are we near important support/resistance levels?
4. What is the probability of a price move in either direction?
5. Should we BUY, SELL, or HOLD (neutral)?

Provide your response in the following JSON format:
{
    "direction": "bullish|bearish|neutral",
    "confidence": 0.0-1.0,
    "reasoning": "Your detailed technical explanation here",
    "patterns_found": ["pattern1", "pattern2", "pattern3"],
    "stop_loss_pct": 0.025,
    "take_profit_pct": 0.04,
    "position_size": 0.15-0.40
}

IMPORTANT GUIDELINES:
- Set "direction" to "neutral" if signals are mixed or weak
- "confidence" should be 0.0-1.0 (0.7+ = strong signal, 0.5-0.7 = moderate, <0.5 = weak)
- List 2-5 specific technical patterns in "patterns_found" (e.g., "RSI oversold + MACD bullish crossover", "Price bouncing off support at $64000")
- Suggest stop_loss_pct and take_profit_pct based on ATR/volatility (typical: 2-3% stop, 3-5% profit)
- Suggest position_size (0.15-0.40) based on confidence and signal strength
- Be conservative - only suggest non-neutral if you see clear technical setup

Response:"""
        
        return prompt
    
    @staticmethod
    def _format_trade_context(trade_context: Dict) -> str:
        """
        Format trade context section of the prompt
        
        Args:
            trade_context: Dict with historical trade statistics
            
        Returns:
            Formatted trade context string
        """
        # Check if RAG was used (provides more detailed context)
        if trade_context.get('rag_enabled', False):
            context_str = f"""
=== SIMILAR PAST TRADES (RAG-Retrieved) ===
Found {trade_context['total_trades']} trades with similar market conditions:
- Winners: {trade_context['winning_trades']} ({trade_context['win_rate']:.1f}% win rate)
- Losers: {trade_context['losing_trades']}
- Avg Win: ${trade_context['avg_winning_pnl']:.2f} | Avg Loss: ${trade_context['avg_losing_pnl']:.2f}
- Net P&L from similar setups: ${trade_context['total_pnl']:.2f}

Top 5 Most Similar Trades:
"""
            for i, trade in enumerate(trade_context.get('similar_trades_detail', []), 1):
                outcome = "WIN" if trade['pnl'] > 0 else "LOSS"
                context_str += (
                    f"  {i}. {trade['side'].upper()} @ ${trade['entry_price']:.2f} → "
                    f"{outcome} ({trade['pnl_pct']:+.2f}%) - Exit: {trade['exit_reason']}\n"
                )
            
            context_str += "\nℹ️  These trades had similar RSI, MACD, and trend conditions to the current market.\n"
        else:
            # Standard trade context (non-RAG)
            context_str = f"""
=== YOUR BOT'S RECENT PERFORMANCE (Context) ===
- Recent Trades: {trade_context['total_trades']} ({trade_context['winning_trades']} wins, {trade_context['losing_trades']} losses)
- Win Rate: {trade_context['win_rate']:.1f}%
- Total P&L: ${trade_context['total_pnl']:.2f}
"""
        
        return context_str
