import asyncio
import logging
from datetime import datetime
import base58
# import requests # No longer used directly, will use aiohttp
import aiohttp
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
        self.session: Optional[aiohttp.ClientSession] = None
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

    async def initialize_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
            logger.info("Trader HTTP session initialized.")

    async def close_session(self):
        if self.session:
            await self.session.close()
            logger.info("Trader HTTP session closed.")

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
                entry_price = await self.get_token_price(token_address) # This now returns Optional[float]
                if entry_price is not None and entry_price > 0: # Ensure entry_price is valid
                    self.active_positions[token_address] = {
                        'entry_price': entry_price,
                        'amount': amount,
                        'stop_loss': entry_price * (1 - self.stop_loss_pct),
                        'take_profit': entry_price * (1 + self.take_profit_pct)
                    }
                    logger.info(f"PREVIEW MODE: Opened position for {token_address} at {entry_price:.6f}, Amount: {amount}")
                elif entry_price is None:
                    logger.error(f"Could not obtain entry price for {token_address}. Buy order not placed.")
                else: # entry_price is 0 or negative
                    logger.warning(f"Entry price for {token_address} is {entry_price}. Buy order not placed.")

            else: # Selling
                position = self.active_positions.get(token_address)
                if position:
                    current_price = await self.get_token_price(token_address)
                    if current_price is not None and current_price > 0: # Ensure current_price is valid
                        profit_loss = (current_price - position['entry_price']) / position['entry_price'] * 100
                        self.update_metrics(profit_loss) # update_metrics should be called before deleting
                        logger.info(f"PREVIEW MODE: Closing position for {token_address} at {current_price:.6f}, Entry: {position['entry_price']:.6f}, P/L: {profit_loss:.2f}%")
                        del self.active_positions[token_address]
                    elif current_price is None:
                        logger.error(f"Could not obtain current price for {token_address} to sell. Position {token_address} remains open.")
                    else: # current_price is 0 or negative
                        logger.warning(f"Current price for {token_address} is {current_price}. Sell order for {token_address} not executed.")
            
            return True # Original logic returned True even if sub-operations failed.
        # If not preview mode, original logic returned False.
        # This part of the logic regarding actual trading execution is unchanged.
        return False

    async def manage_positions(self):
        """Actively manage open positions. This is called repeatedly by start_trading."""
        if not self.session or self.session.closed:
            # This check is more of a safeguard. Session should be managed by start_trading's lifecycle.
            logger.warning("Session not available in manage_positions. Attempting to initialize.")
            await self.initialize_session()
            if not self.session or self.session.closed:
                logger.error("Failed to ensure session is active in manage_positions. Cannot manage positions.")
                return


        active_position_keys = list(self.active_positions.keys()) # Iterate over a copy of keys
        if not active_position_keys:
            logger.info("No active positions to manage in this cycle.")
            return

        logger.info(f"Managing {len(active_position_keys)} active positions...")
        for token_address in active_position_keys:
            # Ensure position still exists before trying to manage, it might have been closed by another task
            if token_address not in self.active_positions:
                logger.debug(f"Position for {token_address} was closed before management cycle. Skipping.")
                continue

            position = self.active_positions[token_address] # Now we can safely get it

            current_price = await self.get_token_price(token_address)

            if current_price is None:
                logger.warning(f"Could not get price for {token_address} during position management. Skipping this cycle for this token.")
                continue # Skip to next token

            if current_price <= 0: # Unlikely for valid tokens, but good to check
                logger.warning(f"Current price for {token_address} is non-positive ({current_price}). Skipping management cycle for this token.")
                continue # Skip to next token

            # Re-check if position exists, as execute_trade is async and might have removed it
            # during the await for get_token_price or if multiple manage_positions run concurrently (though they shouldn't).
            if token_address not in self.active_positions:
                logger.info(f"Position for {token_address} was closed during price fetch. Skipping management actions.")
                continue

            # Ensure position variable is up-to-date if it could change
            # For this flow, position taken at start of loop for this token_address is fine.

            if current_price <= position['stop_loss']:
                logger.info(f"Stop loss triggered for {token_address} at price {current_price:.6f} (SL: {position['stop_loss']:.6f})")
                await self.execute_trade(token_address, position['amount'], is_buy=False)

            elif current_price >= position['take_profit']:
                logger.info(f"Take profit triggered for {token_address} at price {current_price:.6f} (TP: {position['take_profit']:.6f})")
                await self.execute_trade(token_address, position['amount'], is_buy=False)
            # No sleep here as start_trading has its own sleep.

    async def check_token_contract(self, token_address):
        """
        Placeholder: Simulate contract verification.

        Current Behavior:
        - This function is a placeholder and currently returns `True` for any token address,
          effectively bypassing any actual contract verification.
        - It is used in `start_trading` to decide if a token is safe to trade.

        Intended Functionality:
        - To verify the legitimacy and safety of a Solana token contract.
        - This could involve checking for:
            - Renounced mint/freeze authority.
            - Verified source code (if applicable through platforms like Solscan or RugCheck).
            - Liquidity lock status and duration (e.g., via services like Streamflow, Raydium, or custom on-chain checks).
            - Holder distribution to identify potential rug pulls (e.g., few holders with large percentages).
            - Presence of malicious functions or common scam patterns in the contract code if source is available.
            - Known scam token databases or community blacklists.

        Implementation Suggestions:
        - APIs:
            - RugCheck.xyz API: Provides risk scores and details about tokens.
            - GoPlus Security API (gopluslabs.io): Offers token security detection.
            - Birdeye API / DexScreener API: May provide some contract details or links to explorers.
            - Dedicated Solana RPC node: For on-chain data fetching (e.g., account info for LP tokens, mint authority).
        - Libraries:
            - `@solana/web3.js` (if using Node.js bridge) or `solders` / `solana-py` (Python) for direct on-chain interaction.
        - On-chain checks:
            - Fetching mint account data to check `mint_authority_option` and `freeze_authority_option`.
            - Checking LP token accounts for lockups (this can be complex, often requiring parsing specific locker contract states).

        Security Considerations (for a real implementation):
        - API Key Management: If using third-party APIs, API keys must be stored securely (e.g., environment variables, secrets manager)
          and not exposed in the codebase.
        - Rate Limiting: Be mindful of API rate limits. Implement retries with backoff.
        - Data Trust: Information from APIs or on-chain can be manipulated or misinterpreted. Cross-referencing multiple sources is advisable.
        - RPC Node Reliability: If using a public RPC node, consider its reliability and potential for providing stale or manipulated data.
          A private RPC node might be more secure but adds cost.
        - Complexity: Smart contract analysis is complex. Relying solely on automated checks can be risky. Scammers constantly evolve.

        Current Placeholder Safety:
        - Returning `True` is safe for preview/simulation mode as no real funds are involved.
        - For live trading, this function MUST be implemented robustly.
        """
        # In its current placeholder state, always returning True.
        # This is safe for simulation as no real trades occur.
        # For live trading, this MUST be replaced with actual contract checks.
        return True

    async def get_wallet_balance(self):
        """
        Placeholder: Get simulated wallet balance.

        Current Behavior:
        - This function is a placeholder and returns a fixed value of `10.0` (simulating 10 SOL).
        - It is used by `calculate_position_size` to determine how much can be traded.

        Intended Functionality:
        - To retrieve the actual balance of a specified token (e.g., SOL or USDC) in the trading wallet.
        - This would involve querying the Solana blockchain for the balance of the associated token account.

        Implementation Suggestions:
        - Libraries:
            - `solana-py` (Python): Use `solana.rpc.api.Client.get_balance()` for SOL balance or
              `solana.rpc.api.Client.get_token_account_balance()` for SPL token balances.
            - `@solana/web3.js` (if using a Node.js bridge).
        - RPC Calls:
            - Directly use Solana JSON-RPC methods `getBalance` (for SOL) or `getTokenAccountBalance` (for SPL tokens).
            - This requires knowing the public key of the wallet for SOL balance, or the public key of the
              specific SPL token account.

        Security Considerations (for a real implementation):
        - Wallet Interaction:
            - Read-only access: Fetching balance is a read-only operation and generally safe if done correctly.
            - Private Key Security: The private key of the wallet (needed for actual trading, not just balance checks)
              MUST be stored with extreme care (e.g., hardware wallet, secure enclave, heavily protected environment variables
              or a dedicated secrets management service). It should NEVER be hardcoded.
            - Wallet Address Exposure: The wallet's public address will be used in RPC calls, which is public information.
        - RPC Node Security:
            - Ensure connections to the Solana RPC node are secure (HTTPS).
            - Use a trusted RPC provider or your own node. Public nodes can be rate-limited or potentially return manipulated data,
              though this is less likely for simple balance checks.
        - Error Handling: Implement robust error handling for network issues or RPC errors.

        Current Placeholder Safety:
        - Returning a fixed value `10.0` is safe for preview/simulation mode.
        - It does not interact with any real wallet or keys.
        """
        # In its current placeholder state, returns a fixed balance.
        # This is safe for simulation. For live trading, this must query the actual wallet.
        return 10.0  # Simulated 10 SOL balance

    async def get_token_price(self, token_address: str) -> Optional[float]:
        """Get token price from DexScreener API using aiohttp."""
        if not self.session or self.session.closed:
            logger.warning("Aiohttp session not initialized or closed in get_token_price. Ensuring it's initialized.")
            await self.initialize_session()
            if not self.session: # Should not happen if initialize_session works
                 logger.error("Failed to initialize session in get_token_price.")
                 return None


        # Assuming DEXSCREENER_API is available from config import (from .config import *)
        # This was how scanner.py used it. If not available, this will cause a NameError.
        # For robustness, direct access to config variable might be better if it's guaranteed.
        # from .config import DEXSCREENER_API
        url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"

        try:
            async with self.session.get(url) as response:
                response.raise_for_status()  # Raises HTTPError for bad responses (4xx or 5xx)
                data = await response.json(content_type=None) # content_type=None to handle potential non-application/json responses if API behaves unexpectedly

                if not data:
                    logger.warning(f"No data received from DexScreener for token {token_address}")
                    return None

                pairs = data.get('pairs')
                if not pairs or not isinstance(pairs, list) or len(pairs) == 0:
                    logger.warning(f"No pairs found or invalid pairs structure in DexScreener response for token {token_address}. Data: {data}")
                    return None

                first_pair = pairs[0]
                if not isinstance(first_pair, dict):
                    logger.warning(f"First pair is not a dictionary for token {token_address}. Pair: {first_pair}")
                    return None

                price_usd_str = first_pair.get('priceUsd')
                if price_usd_str is None: # Could be missing or explicitly null
                    logger.warning(f"No 'priceUsd' (or it was null) in first pair for token {token_address}. Pair: {first_pair}")
                    return None

                try:
                    price_usd = float(price_usd_str)
                    return price_usd
                except (ValueError, TypeError) as e:
                    logger.error(f"Invalid 'priceUsd' format ('{price_usd_str}') for token {token_address}: {e}")
                    return None

        except aiohttp.ClientResponseError as http_err:
            logger.error(f"HTTP error fetching price for {token_address} from {url}: {http_err}")
            return None
        except aiohttp.ContentTypeError as ct_err: # For JSON decoding issues
            logger.error(f"JSON decode error (content type) fetching price for {token_address} from {url}: {ct_err}")
            return None
        except Exception as e: # Catch-all for other unexpected errors
            logger.error(f"Unexpected error fetching price for {token_address} from {url}: {e}", exc_info=True)
            return None

    async def get_price_history(self, token_address):
        """
        Placeholder: Get historical price data for a token.

        Current Behavior:
        - This function is a placeholder and returns a fixed list of mock prices.
        - It is used by `should_trade` to calculate technical indicators.

        Intended Functionality:
        - To retrieve historical price data (e.g., OHLCV - Open, High, Low, Close, Volume) for a given token address
          over a specific period and resolution (e.g., 1-minute candles for the last 24 hours).
        - This data is crucial for calculating most technical indicators.

        Implementation Suggestions:
        - APIs:
            - DexScreener API: Provides candlestick data (`/dex/ohlcv/solana/{pair_address}?res={resolution}&span={timespan}`).
            - Birdeye API: Also offers OHLCV data for tokens and pairs.
            - Dedicated crypto data providers like CoinGecko, CoinMarketCap, Kaiko, or CCXT library (which wraps many exchanges).
              However, these might be more focused on CEX data or major tokens, rather than all Solana SPL tokens.
            - Jupiter API: While primarily for swaps, it might offer price feeds or historical data for routing purposes.
        - Libraries:
            - `aiohttp` or `requests` for making HTTP calls to the chosen API.
            - `pandas` for data manipulation if the API returns data that needs reshaping or cleaning.
        - Data Format: Ensure the data is processed into a list of prices (or a more structured format like a pandas DataFrame
          if OHLC data is used) suitable for technical indicator calculation libraries.

        Security Considerations (for a real implementation):
        - API Key Management: If the chosen API requires an API key, it must be stored securely (e.g., environment variables,
          cloud secrets manager) and not hardcoded.
        - Data Integrity: Verify the source of the data. Use reputable APIs. Stale or inaccurate historical data can lead to
          poor trading decisions.
        - Rate Limiting: Be aware of API rate limits. Implement caching or respectful polling intervals.
        - Error Handling: Robustly handle API errors, network issues, or unexpected data formats.

        Current Placeholder Safety:
        - Returning a fixed list of numbers is safe for preview/simulation mode.
        - It does not make any external calls or handle sensitive data.
        """
        # In its current placeholder state, returns a fixed list of mock prices.
        # This is safe for simulation. For live trading, this must fetch real historical data.
        # Example: return await fetch_real_price_history(token_address, resolution="15m", limit=100)
        return [100.0, 102.0, 101.5, 103.0, 102.5, 104.0, 105.0, 103.5, 106.0, 107.0,
                105.0, 104.5, 106.5, 108.0, 107.0, 109.0, 110.0, 108.5, 109.5, 112.0] # 20 data points

    async def get_volume_history(self, token_address):
        """
        Placeholder: Get historical volume data for a token.

        Current Behavior:
        - This function is a placeholder and returns a fixed list of mock volumes.
        - It is used by `should_trade` to calculate volume-based technical indicators (e.g., OBV, volume ratio).

        Intended Functionality:
        - To retrieve historical trading volume data for a given token address, corresponding to the same period and
          resolution as `get_price_history`.
        - Volume data is essential for many technical analysis strategies.

        Implementation Suggestions:
        - APIs: The same APIs suggested for `get_price_history` (DexScreener, Birdeye, etc.) usually provide volume data
          as part of their OHLCV responses.
        - Data Extraction: Ensure that the volume component is correctly extracted from the API response.
          The volume should correspond to the base token, not the quote token, or be the total volume in USD.
        - Consistency: The fetched volume data must align chronologically with the price data from `get_price_history`.

        Security Considerations (for a real implementation):
        - (Same as `get_price_history` regarding API key management, data integrity, rate limiting, and error handling).
        - Wash Trading: Be aware that trading volumes on DEXs can sometimes be artificially inflated by wash trading.
          While hard to detect perfectly, unusually high volume with little price change or from very few wallets
          could be a red flag. This is more of a data interpretation issue than a direct security vulnerability
          of the function itself.

        Current Placeholder Safety:
        - Returning a fixed list of numbers is safe for preview/simulation mode.
        - It does not make any external calls or handle sensitive data.
        """
        # In its current placeholder state, returns a fixed list of mock volumes.
        # This is safe for simulation. For live trading, this must fetch real historical data.
        # Ensure this data aligns with the price history data points.
        return [1000.0, 1200.0, 1100.0, 1300.0, 1400.0, 1500.0, 1350.0, 1600.0, 1700.0, 1550.0,
                1450.0, 1650.0, 1800.0, 1750.0, 1900.0, 2000.0, 1850.0, 1950.0, 2200.0, 2100.0] # 20 data points

    async def start_trading(self, scanner):
        """Start trading based on scanner results"""
        logger.info("Starting preview trading bot with enhanced monitoring...")
        await self.initialize_session() # Initialize session before starting the loop
        
        try: # Outer try for session cleanup
            while True: # Main trading loop
                try:
                    self.performance_metrics['scans'] += 1
                    # Ensure scanner object is valid and its method is callable
                    if scanner and hasattr(scanner, 'get_potential_tokens') and callable(scanner.get_potential_tokens):
                        potential_tokens = scanner.get_potential_tokens()
                    else:
                        logger.error("Scanner or get_potential_tokens method is not available. Cannot proceed.")
                        await asyncio.sleep(60) # Wait before retrying
                        continue

                    if potential_tokens: # Check if there are any tokens to process
                        logger.info(f"Received {len(potential_tokens)} potential tokens from scanner.")
                        self.performance_metrics['potential_trades'] = len(potential_tokens)

                        for token_data in potential_tokens:
                            if not isinstance(token_data, dict):
                                logger.warning(f"Invalid token data format from scanner: {token_data}. Skipping.")
                                continue

                            token_address = token_data.get('address')
                            token_symbol = token_data.get('symbol', 'N/A') # Default symbol if missing

                            if not token_address:
                                logger.warning(f"Token data missing 'address': {token_data}. Skipping.")
                                continue

                            if token_address not in self.active_positions:
                                if await self.check_token_contract(token_address): # Simulated
                                    # should_trade uses its own get_price_history, which is placeholder.
                                    # For now, this remains as is.
                                    should_trade_flag, reason = await self.should_trade(token_address)
                                    if should_trade_flag:
                                        scanner_price_str = token_data.get('price')
                                        try:
                                            current_price_for_sizing = float(scanner_price_str) if scanner_price_str is not None else None
                                        except (ValueError, TypeError) as e:
                                            logger.warning(f"Invalid price format ('{scanner_price_str}') from scanner for {token_symbol}. Skipping trade. Error: {e}")
                                            continue

                                        if current_price_for_sizing is None or current_price_for_sizing <= 0:
                                            logger.warning(f"Cannot calculate position size for {token_symbol} due to invalid price: {current_price_for_sizing}. Skipping trade.")
                                            continue

                                        # Volatility is hardcoded to 0.5, should ideally be calculated or fetched.
                                        position_size = await self.calculate_position_size(current_price_for_sizing, 0.5)

                                        if position_size > 0:
                                            logger.info(f"Attempting to execute buy for {token_symbol} ({token_address}), Size: {position_size}, Scanner Price: {current_price_for_sizing:.6f}, Reason: {reason}")
                                            if await self.execute_trade(token_address, position_size, is_buy=True):
                                                # execute_trade now logs its own success/failure for opening position.
                                                # Log additional details from scanner
                                                logger.info(f"  Scanner Data for {token_symbol}: Liquidity=${token_data.get('liquidity', 0):,.0f}, Vol24h=${token_data.get('volume_24h', 0):,.0f}, Holders={token_data.get('holders', 0)}")
                                                buy_sell_ratio = token_data.get('buy_sell_ratio', 'N/A')
                                                logger.info(f"  Buy/Sell Ratio: {buy_sell_ratio if isinstance(buy_sell_ratio, str) else f'{buy_sell_ratio:.2f}'}")
                                        else:
                                            logger.info(f"Position size for {token_symbol} is zero. Skipping trade.")
                                    # else: # Optional: log why not trading if reason is informative
                                        # logger.debug(f"Not trading {token_symbol} ({token_address}). Reason: {reason}")
                            # else: # Already in active positions
                                # logger.debug(f"Token {token_symbol} ({token_address}) is already in active positions. Skipping buy consideration.")

                    else: # No potential tokens
                        logger.info("No potential tokens from scanner in this cycle.")


                    # Manage existing positions - original code called this inside the main loop.
                    if self.active_positions:
                        # manage_positions itself logs how many it's managing or if none.
                        await self.manage_positions()
                    else:
                        logger.info("No active positions to manage in this cycle (checked in start_trading).")


                    # Log performance metrics (e.g., every 5 scans)
                    if self.performance_metrics['scans'] % 5 == 0:
                        self.log_metrics()

                    await asyncio.sleep(60)  # Main loop delay
                
                except KeyboardInterrupt: # Graceful shutdown on Ctrl+C
                    logger.info("KeyboardInterrupt received. Shutting down trader...")
                    break # Exit the while True loop
                except Exception as e: # Catch errors within the while True loop iteration
                    logger.error(f"Critical error in trading loop iteration: {e}", exc_info=True)
                    logger.info("Attempting to recover and continue after a short delay...")
                    await asyncio.sleep(30) # Longer delay after a critical error before retrying loop
        finally:
            logger.info("Closing trader HTTP session...")
            await self.close_session() # Ensure session is closed when trading stops or on error

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
