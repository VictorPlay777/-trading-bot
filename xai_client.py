"""
xAI (Grok) API Client for trading signals
"""
import requests
import json
import logging
from typing import Dict, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class GrokSignal:
    """Signal from Grok"""
    direction: str  # "long" or "short"
    confidence: float  # 0.0 to 1.0
    reason: str
    raw_response: str


class XAIClient:
    """xAI Grok API Client"""
    
    def __init__(self, api_key: str, base_url: str = "https://api.x.ai/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        self.timeout = 30
    
    def generate_trading_signal(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        model: str = "grok-4.20-reasoning"
    ) -> Optional[GrokSignal]:
        """
        Generate trading signal using Grok
        
        Args:
            symbol: Trading symbol (e.g., BTCUSDT)
            market_data: Dictionary with market context
                - price: current price
                - volume: recent volume
                - ema_short: short EMA
                - ema_long: long EMA
                - rsi: RSI value
                - atr: ATR value
                - trend: current trend description
            model: Grok model to use
            
        Returns:
            GrokSignal if successful, None otherwise
        """
        prompt = self._build_prompt(symbol, market_data)
        
        try:
            response = requests.post(
                f"{self.base_url}/responses",
                headers=self.headers,
                json={
                    "model": model,
                    "input": prompt
                },
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                logger.error(f"xAI API error {response.status_code}: {response.text}")
                return None
            
            data = response.json()
            raw_response = data.get("output", {}).get("text", "")
            
            # Parse the response
            signal = self._parse_signal(raw_response, symbol)
            
            if signal:
                logger.info(f"Grok signal for {symbol}: {signal.direction} conf={signal.confidence:.2f} reason={signal.reason}")
            
            return signal
            
        except requests.exceptions.Timeout:
            logger.error(f"xAI API timeout for {symbol}")
            return None
        except Exception as e:
            logger.error(f"xAI API error for {symbol}: {e}")
            return None
    
    def _build_prompt(self, symbol: str, market_data: Dict[str, Any]) -> str:
        """Build prompt for Grok"""
        price = market_data.get("price", 0)
        volume = market_data.get("volume", 0)
        ema_short = market_data.get("ema_short", 0)
        ema_long = market_data.get("ema_long", 0)
        rsi = market_data.get("rssi", 50)
        atr = market_data.get("atr", 0)
        trend = market_data.get("trend", "neutral")
        
        prompt = f"""You are a trading signal generator for cryptocurrency futures.

Symbol: {symbol}
Current price: ${price:.2f}
24h volume: ${volume:,.0f}
EMA short: ${ema_short:.2f}
EMA long: ${ema_long:.2f}
RSI: {rsi:.1f}
ATR: {atr:.2f}
Trend: {trend}

Analyze this market data and provide a trading signal.

Respond in this exact format:
DIRECTION: [long/short/neutral]
CONFIDENCE: [0.0 to 1.0]
REASON: [brief explanation in 1 sentence]

Example response:
DIRECTION: long
CONFIDENCE: 0.75
REASON: Strong bullish momentum with RSI oversold and volume spike.
"""
        return prompt
    
    def _parse_signal(self, response: str, symbol: str) -> Optional[GrokSignal]:
        """Parse Grok response into signal"""
        try:
            lines = response.strip().split('\n')
            direction = "neutral"
            confidence = 0.5
            reason = "No clear signal"
            
            for line in lines:
                line = line.strip()
                if line.startswith("DIRECTION:"):
                    direction = line.split(":")[1].strip().lower()
                elif line.startswith("CONFIDENCE:"):
                    try:
                        confidence = float(line.split(":")[1].strip())
                    except:
                        confidence = 0.5
                elif line.startswith("REASON:"):
                    reason = line.split(":", 1)[1].strip()
            
            # Validate direction
            if direction not in ["long", "short", "neutral"]:
                direction = "neutral"
            
            # Validate confidence
            confidence = max(0.0, min(1.0, confidence))
            
            # If neutral or low confidence, return None
            if direction == "neutral" or confidence < 0.6:
                return None
            
            return GrokSignal(
                direction=direction,
                confidence=confidence,
                reason=reason,
                raw_response=response
            )
            
        except Exception as e:
            logger.error(f"Error parsing Grok response for {symbol}: {e}")
            return None
    
    def test_connection(self) -> bool:
        """Test API connection"""
        try:
            response = requests.post(
                f"{self.base_url}/responses",
                headers=self.headers,
                json={
                    "model": "grok-4.20-reasoning",
                    "input": "Say 'API connected' if you can read this."
                },
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"xAI connection test failed: {e}")
            return False
