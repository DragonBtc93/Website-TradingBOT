import asyncio
import logging
from datetime import datetime
import base58
import requests
import pandas as pd
import numpy as np
from typing import Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class SolanaTrader:
    def __init__(self):
        self.active_positions = {}
        self.position_history = []
        self.is_preview = True
        self.performance_metrics = {
            'scans': 0,
            'potential_trades': 0,
            'executed_trades': 0,
            'successful_trades': 0,
            'failed_trades': 0,
            'total_profit_loss': 0,
            'win_rate': 0
        }
        # Risk management parameters
        self.max_position_size = 0.1  # Maximum 10% of portfolio per trade
        self.stop_loss_pct = 0.05     # 5% stop loss
        self.take_profit_pct = 0.15   # 15% take profit
        self.max_drawdown = 0.20      # 20% maximum drawdown
        
        # Technical indicator parameters
        self.macd_params = {'fast': 12, 'slow': 26, 'signal': 9}
        self.bollinger_params = {'window': 20, 'num_std': 2}
        self.stoch_params = {'k_window': 14, 'd_window': 3}
        self.roc_window = 12
        self.ichimoku_params = {
            'tenkan': 9,      # Conversion line period
            'kijun': 26,      # Base line period
            'senkou_span_b': 52,  # Leading Span B period
            'displacement': 26    # Displacement period
        }
        
        logger.info("Starting trader in preview mode with enhanced monitoring")

    async def calculate_technical_indicators(self, price_data: List[float], volume_data: List[float]) -> Dict:
        """Calculate comprehensive technical indicators for analysis"""
        prices = np.array(price_data)
        volumes = np.array(volume_data)
        
        # Basic indicators from before
        ma_20 = np.mean(prices[-20:]) if len(prices) >= 20 else np.mean(prices)
        ma_50 = np.mean(prices[-50:]) if len(prices) >= 50 else np.mean(prices)
        
        # RSI calculation
        diff = np.diff(prices)
        gains = np.where(diff > 0, diff, 0)
        losses = np.where(diff < 0, -diff, 0)
        avg_gain = np.mean(gains[-14:]) if len(gains) >= 14 else np.mean(gains)
        avg_loss = np.mean(losses[-14:]) if len(losses) >= 14 else np.mean(losses)
        rs = avg_gain / avg_loss if avg_loss != 0 else 0
        rsi = 100 - (100 / (1 + rs))

        # MACD calculation
        exp1 = pd.Series(prices).ewm(span=self.macd_params['fast']).mean()
        exp2 = pd.Series(prices).ewm(span=self.macd_params['slow']).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=self.macd_params['signal']).mean()
        macd_hist = macd - signal
        
        # Bollinger Bands
        bb_ma = pd.Series(prices).rolling(window=self.bollinger_params['window']).mean()
        bb_std = pd.Series(prices).rolling(window=self.bollinger_params['window']).std()
        bb_upper = bb_ma + (bb_std * self.bollinger_params['num_std'])
        bb_lower = bb_ma - (bb_std * self.bollinger_params['num_std'])
        
        # Stochastic Oscillator
        low_min = pd.Series(prices).rolling(window=self.stoch_params['k_window']).min()
        high_max = pd.Series(prices).rolling(window=self.stoch_params['k_window']).max()
        k = 100 * (prices[-1] - low_min.iloc[-1]) / (high_max.iloc[-1] - low_min.iloc[-1])
        d = pd.Series([k]).rolling(window=self.stoch_params['d_window']).mean().iloc[-1]
        
        # On-Balance Volume (OBV)
        obv = np.zeros_like(volumes)
        obv[0] = volumes[0]
        for i in range(1, len(volumes)):
            if prices[i] > prices[i-1]:
                obv[i] = obv[i-1] + volumes[i]
            elif prices[i] < prices[i-1]:
                obv[i] = obv[i-1] - volumes[i]
            else:
                obv[i] = obv[i-1]
        
        # Price Rate of Change (ROC)
        roc = ((prices[-1] - prices[-self.roc_window]) / prices[-self.roc_window]) * 100 if len(prices) > self.roc_window else 0
        
        # Volume analysis
        avg_volume = np.mean(volumes)
        vol_ratio = volumes[-1] / avg_volume if avg_volume != 0 else 1
        
        # Calculate Ichimoku Cloud
        ichimoku = await self.calculate_ichimoku(prices)
        
        # Add Ichimoku indicators if available
        if ichimoku:
            return {
                'ma_20': ma_20,
                'ma_50': ma_50,
                'rsi': rsi,
                'volume_ratio': vol_ratio,
                'macd': macd.iloc[-1],
                'macd_signal': signal.iloc[-1],
                'macd_hist': macd_hist.iloc[-1],
                'bb_upper': bb_upper.iloc[-1],
                'bb_lower': bb_lower.iloc[-1],
                'bb_ma': bb_ma.iloc[-1],
                'stoch_k': k,
                'stoch_d': d,
                'obv': obv[-1],
                'obv_change': obv[-1] - obv[-2] if len(obv) > 1 else 0,
                'roc': roc,
                'tenkan_sen': ichimoku['tenkan_sen'],
                'kijun_sen': ichimoku['kijun_sen'],
                'senkou_span_a': ichimoku['senkou_span_a'],
                'senkou_span_b': ichimoku['senkou_span_b'],
                'chikou_span': ichimoku['chikou_span'],
                'cloud_top': ichimoku['cloud_top'],
                'cloud_bottom': ichimoku['cloud_bottom'],
                'cloud_direction': ichimoku['cloud_direction']
            }
        else:
            return {
                'ma_20': ma_20,
                'ma_50': ma_50,
                'rsi': rsi,
                'volume_ratio': vol_ratio,
                'macd': macd.iloc[-1],
                'macd_signal': signal.iloc[-1],
                'macd_hist': macd_hist.iloc[-1],
                'bb_upper': bb_upper.iloc[-1],
                'bb_lower': bb_lower.iloc[-1],
                'bb_ma': bb_ma.iloc[-1],
                'stoch_k': k,
                'stoch_d': d,
                'obv': obv[-1],
                'obv_change': obv[-1] - obv[-2] if len(obv) > 1 else 0,
                'roc': roc
            }

    async def calculate_ichimoku(self, prices: np.ndarray) -> Dict:
        """Calculate Ichimoku Cloud components"""
        try:
            df = pd.DataFrame({'price': prices})
            
            # Tenkan-sen (Conversion Line)
            high_9 = df['price'].rolling(window=self.ichimoku_params['tenkan']).max()
            low_9 = df['price'].rolling(window=self.ichimoku_params['tenkan']).min()
            tenkan_sen = (high_9 + low_9) / 2
            
            # Kijun-sen (Base Line)
            high_26 = df['price'].rolling(window=self.ichimoku_params['kijun']).max()
            low_26 = df['price'].rolling(window=self.ichimoku_params['kijun']).min()
            kijun_sen = (high_26 + low_26) / 2
            
            # Senkou Span A (Leading Span A)
            senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(self.ichimoku_params['displacement'])
            
            # Senkou Span B (Leading Span B)
            high_52 = df['price'].rolling(window=self.ichimoku_params['senkou_span_b']).max()
            low_52 = df['price'].rolling(window=self.ichimoku_params['senkou_span_b']).min()
            senkou_span_b = ((high_52 + low_52) / 2).shift(self.ichimoku_params['displacement'])
            
            # Chikou Span (Lagging Span)
            chikou_span = df['price'].shift(-self.ichimoku_params['displacement'])
            
            return {
                'tenkan_sen': tenkan_sen.iloc[-1],
                'kijun_sen': kijun_sen.iloc[-1],
                'senkou_span_a': senkou_span_a.iloc[-1],
                'senkou_span_b': senkou_span_b.iloc[-1],
                'chikou_span': chikou_span.iloc[-1] if len(chikou_span.dropna()) > 0 else None,
                'current_price': prices[-1],
                'cloud_top': max(senkou_span_a.iloc[-1], senkou_span_b.iloc[-1]),
                'cloud_bottom': min(senkou_span_a.iloc[-1], senkou_span_b.iloc[-1]),
                'cloud_direction': 1 if senkou_span_a.iloc[-1] > senkou_span_b.iloc[-1] else -1
            }
        except Exception as e:
            logger.error(f"Error calculating Ichimoku Cloud: {e}")
            return None

    async def should_trade(self, token_address: str) -> tuple[bool, str]:
        """Determine if we should enter a trade based on multiple factors"""
        try:
            # Get historical price data (implement your data fetching logic)
            price_history = await self.get_price_history(token_address)
            volume_history = await self.get_volume_history(token_address)
            
            if not price_history or not volume_history:
                return False, "Insufficient historical data"

            # Calculate technical indicators
            indicators = await self.calculate_technical_indicators(price_history, volume_history)
            current_price = price_history[-1]
            
            # Enhanced trading signals with Ichimoku Cloud
            signals = {
                'trend': indicators['ma_20'] > indicators['ma_50'],
                'rsi_oversold': indicators['rsi'] < 30,
                'volume_spike': indicators['volume_ratio'] > 1.5,
                'macd_bullish': indicators['macd_hist'] > 0 and indicators['macd'] > indicators['macd_signal'],
                'bb_oversold': current_price < indicators['bb_lower'],
                'stoch_oversold': indicators['stoch_k'] < 20 and indicators['stoch_d'] < 20,
                'obv_increasing': indicators['obv_change'] > 0,
                'roc_positive': indicators['roc'] > 0,
                # Ichimoku Cloud signals
                'price_above_cloud': current_price > indicators['cloud_top'],
                'bullish_cloud': indicators['cloud_direction'] > 0,
                'tenkan_kijun_cross': (indicators['tenkan_sen'] > indicators['kijun_sen'] and
                                     indicators['tenkan_sen'] > indicators['cloud_top']),
                'chikou_confirmation': (indicators['chikou_span'] is not None and 
                                     indicators['chikou_span'] > current_price)
            }
            
            # Calculate signal strength (0-100%)
            signal_strength = (sum(signals.values()) / len(signals)) * 100
            
            # Enhanced decision logic with Ichimoku Cloud
            primary_signals = (
                signals['trend'] and 
                signals['macd_bullish'] and 
                signals['volume_spike'] and
                signals['price_above_cloud']
            )
            
            ichimoku_signals = (
                signals['bullish_cloud'] and 
                signals['tenkan_kijun_cross']
            )
            
            secondary_signals = (
                signals['rsi_oversold'] or 
                signals['bb_oversold'] or 
                signals['stoch_oversold']
            )
            
            # Strong buy signal when all conditions align
            if primary_signals and ichimoku_signals and secondary_signals:
                return True, f"Strong buy signal ({signal_strength:.1f}% confidence)"
            
            # Moderate buy signal with some confirmations
            if primary_signals and (ichimoku_signals or secondary_signals):
                if signal_strength > 65:  # Increased threshold with Ichimoku
                    return True, f"Moderate buy signal ({signal_strength:.1f}% confidence)"
            
            return False, f"Insufficient signals ({signal_strength:.1f}% confidence)"
            
        except Exception as e:
            logger.error(f"Error in trade analysis: {e}")
            return False, f"Analysis error: {str(e)}"

    async def execute_trade(self, token_address: str, amount: float, is_buy: bool = True) -> bool:
        """Execute trade with enhanced risk management"""
        if self.is_preview:
            action = "BUY" if is_buy else "SELL"
            logger.info(f"PREVIEW MODE: Would {action} {amount} SOL worth of {token_address}")
            
            if is_buy:
                entry_price = await self.get_token_price(token_address)
                if entry_price > 0:
                    self.active_positions[token_address] = {
                        'entry_price': entry_price,
                        'amount': amount,
                        'stop_loss': entry_price * (1 - self.stop_loss_pct),
                        'take_profit': entry_price * (1 + self.take_profit_pct)
                    }
            else:
                position = self.active_positions.get(token_address)
                if position:
                    current_price = await self.get_token_price(token_address)
                    if current_price > 0:
                        profit_loss = (current_price - position['entry_price']) / position['entry_price'] * 100
                        self.update_metrics(profit_loss)
                        del self.active_positions[token_address]
            
            return True
        return False

    async def manage_positions(self):
        """Actively manage open positions"""
        while True:
            for token_address, position in list(self.active_positions.items()):
                current_price = await self.get_token_price(token_address)
                
                if current_price <= position['stop_loss']:
                    logger.info(f"Stop loss triggered for {token_address}")
                    await self.execute_trade(token_address, position['amount'], is_buy=False)
                
                elif current_price >= position['take_profit']:
                    logger.info(f"Take profit triggered for {token_address}")
                    await self.execute_trade(token_address, position['amount'], is_buy=False)
                
            await asyncio.sleep(60)  # Check positions every minute

    async def check_token_contract(self, token_address):
        """Simulate contract verification in preview mode"""
        return True

    async def get_wallet_balance(self):
        """Get simulated wallet balance"""
        return 10.0  # Simulated 10 SOL balance

    async def get_token_price(self, token_address):
        """Get token price from DexScreener API"""
        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                if data.get('pairs'):
                    return float(data['pairs'][0].get('priceUsd', 0))
            return 0
        except Exception as e:
            logger.error(f"Error getting token price: {e}")
            return 0

    async def get_price_history(self, token_address):
        """Get historical price data (placeholder for API integration)"""
        # Implement your data fetching logic here
        return [100.0, 120.0, 110.0, 130.0, 140.0]

    async def get_volume_history(self, token_address):
        """Get historical volume data (placeholder for API integration)"""
        # Implement your data fetching logic here
        return [1000.0, 1200.0, 1100.0, 1300.0, 1400.0]

    async def start_trading(self, scanner):
        """Start trading based on scanner results"""
        logger.info("Starting preview trading bot with enhanced monitoring...")
        
        while True:
            try:
                self.performance_metrics['scans'] += 1
                potential_tokens = scanner.get_potential_tokens()
                self.performance_metrics['potential_trades'] = len(potential_tokens)
                
                for token in potential_tokens:
                    if token['address'] not in self.active_positions:
                        if await self.check_token_contract(token['address']):
                            should_trade, reason = await self.should_trade(token['address'])
                            if should_trade:
                                position_size = await self.calculate_position_size(float(token['price']), 0.5)
                                if position_size > 0:
                                    if await self.execute_trade(token['address'], position_size, is_buy=True):
                                        logger.info(f"PREVIEW MODE: Opened position for {token['symbol']} with metrics:")
                                        logger.info(f"- Liquidity: ${token['liquidity']:,.0f}")
                                        logger.info(f"- 24h Volume: ${token['volume_24h']:,.0f}")
                                        logger.info(f"- Holders: {token['holders']}")
                                        logger.info(f"- Buy/Sell Ratio: {token['buy_sell_ratio']:.2f}")

                # Manage existing positions
                await self.manage_positions()

                # Log performance metrics every 5 minutes
                if self.performance_metrics['scans'] % 5 == 0:
                    self.log_metrics()

                await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Error in trading loop: {e}")
                await asyncio.sleep(10)

    def log_metrics(self):
        """Log current performance metrics"""
        metrics = self.performance_metrics
        logger.info("\n=== Performance Metrics ===")
        logger.info(f"Total Scans: {metrics['scans']}")
        logger.info(f"Potential Trades Found: {metrics['potential_trades']}")
        logger.info(f"Executed Trades: {metrics['executed_trades']}")
        logger.info(f"Success Rate: {metrics['win_rate']:.1f}%")
        logger.info(f"Total P/L: {metrics['total_profit_loss']:.2f}%")
        logger.info("========================\n")

    def update_metrics(self, trade_result=None):
        """Update performance metrics"""
        if trade_result:
            self.performance_metrics['executed_trades'] += 1
            if trade_result > 0:
                self.performance_metrics['successful_trades'] += 1
            else:
                self.performance_metrics['failed_trades'] += 1
            
            self.performance_metrics['total_profit_loss'] += trade_result
            self.performance_metrics['win_rate'] = (
                self.performance_metrics['successful_trades'] / 
                self.performance_metrics['executed_trades'] * 100
            )

    async def analyze_market_sentiment(self, token_address: str) -> float:
        """Analyze market sentiment using various indicators"""
        try:
            # Get token info and social metrics (placeholder for API integration)
            sentiment_score = 0.5  # Neutral baseline
            
            # Add your preferred sentiment analysis logic here
            # Example factors to consider:
            # - Social media mentions
            # - Trading volume trends
            # - Price momentum
            # - News sentiment
            
            return sentiment_score
        except Exception as e:
            logger.error(f"Error in sentiment analysis: {e}")
            return 0.5

    async def calculate_position_size(self, token_price: float, volatility: float) -> float:
        """Calculate position size based on volatility and risk parameters"""
        balance = await self.get_wallet_balance()
        
        # Adjust position size based on volatility
        vol_factor = 1 - min(volatility, 0.5)  # Reduce size for higher volatility
        base_size = balance * self.max_position_size
        adjusted_size = base_size * vol_factor
        
        return min(adjusted_size, balance * self.max_position_size)
