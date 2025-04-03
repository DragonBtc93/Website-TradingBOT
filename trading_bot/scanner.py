import asyncio
import logging
from datetime import datetime, timedelta
import aiohttp
import pandas as pd
from .config import *

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TokenScanner:
    def __init__(self):
        self.session = None
        self.potential_tokens = []
        self.scan_count = 0

    async def initialize(self):
        self.session = aiohttp.ClientSession()
        logger.info("Token scanner initialized")

    async def close(self):
        if self.session:
            await self.session.close()

    async def fetch_token_data(self, token_address):
        """Fetch detailed token data from DexScreener"""
        try:
            url = f"{DEXSCREENER_API}/tokens/{token_address}"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('pairs', [])[0] if data.get('pairs') else None
                return None
        except Exception as e:
            logger.error(f"Error fetching token data: {e}")
            return None

    async def check_holder_metrics(self, token_data):
        """Analyze holder metrics"""
        try:
            holders = token_data.get('holders', {})
            if not holders:
                return False, "No holder data"

            # Check minimum holder count
            if holders.get('total', 0) < MIN_HOLDER_COUNT:
                return False, f"Insufficient holders: {holders.get('total', 0)}"

            # Check wallet concentration
            top_holder_pct = holders.get('top', {}).get('percentage', 100)
            if top_holder_pct > MAX_WALLET_CONCENTRATION:
                return False, f"High wallet concentration: {top_holder_pct}%"

            return True, "Holder metrics passed"
        except Exception as e:
            logger.error(f"Error checking holder metrics: {e}")
            return False, str(e)

    def analyze_token_metrics(self, token_data):
        """Analyze token metrics based on our criteria"""
        try:
            if not token_data:
                return False, "No token data available"

            # Age check
            created_at = datetime.fromtimestamp(token_data.get('created', 0))
            age_hours = (datetime.now() - created_at).total_seconds() / 3600
            if age_hours > MAX_TOKEN_AGE_HOURS:
                return False, f"Token too old: {age_hours:.1f} hours"

            # Liquidity check
            liquidity_usd = float(token_data.get('liquidity', {}).get('usd', 0))
            if liquidity_usd < MIN_LIQUIDITY:
                return False, f"Insufficient liquidity: ${liquidity_usd:,.0f}"

            # Market cap check
            market_cap = float(token_data.get('fdv', 0))
            if market_cap > MAX_MARKET_CAP:
                return False, f"Market cap too high: ${market_cap:,.0f}"

            # Transaction analysis
            txns_1h = token_data.get('txns', {}).get('h1', {})
            total_txns = txns_1h.get('total', 0)
            if total_txns < MIN_TRANSACTIONS:
                return False, f"Low transaction count: {total_txns}"

            # Buy/Sell ratio analysis
            buys = txns_1h.get('buys', 0)
            sells = txns_1h.get('sells', 0)
            if sells > 0:
                buy_sell_ratio = buys / sells
                if buy_sell_ratio < MIN_BUY_SELL_RATIO:
                    return False, f"Poor buy/sell ratio: {buy_sell_ratio:.2f}"

            # Volume analysis
            volume_24h = float(token_data.get('volume', {}).get('h24', 0))
            volume_1h = float(token_data.get('volume', {}).get('h1', 0))
            if volume_1h > 0:
                volume_spike = volume_1h * 24 / volume_24h
                if volume_spike < VOLUME_SPIKE_THRESHOLD:
                    return False, f"No significant volume spike: {volume_spike:.1f}x"

            # LP Token analysis
            lp_locked = token_data.get('liquidity', {}).get('locked', 0)
            if lp_locked < MIN_LP_LOCKED_PERCENTAGE:
                return False, f"Insufficient LP locked: {lp_locked}%"

            # Price action analysis
            price_change_1h = float(token_data.get('priceChange', {}).get('h1', 0))
            if price_change_1h < -10:  # Avoid tokens in free fall
                return False, f"Significant price drop: {price_change_1h}%"

            return True, "Token passed all checks"
        except Exception as e:
            logger.error(f"Error analyzing token metrics: {e}")
            return False, str(e)

    async def scan_new_tokens(self):
        """Continuously scan for new tokens meeting our criteria"""
        try:
            url = f"{DEXSCREENER_API}/pairs/solana"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    pairs = data.get('pairs', [])
                    
                    self.scan_count += 1
                    logger.info(f"Scanning iteration {self.scan_count}: Found {len(pairs)} pairs")
                    
                    for pair in pairs:
                        passed, reason = self.analyze_token_metrics(pair)
                        if passed:
                            # Additional holder metrics check
                            holder_passed, holder_reason = await self.check_holder_metrics(pair)
                            if not holder_passed:
                                logger.info(f"Token {pair.get('baseToken', {}).get('symbol')} failed holder check: {holder_reason}")
                                continue

                            self.potential_tokens.append({
                                'address': pair.get('dexId'),
                                'symbol': pair.get('baseToken', {}).get('symbol'),
                                'price': pair.get('priceUsd'),
                                'liquidity': pair.get('liquidity', {}).get('usd'),
                                'volume_24h': pair.get('volume', {}).get('h24'),
                                'holders': pair.get('holders', {}).get('total', 0),
                                'buy_sell_ratio': self._calculate_buy_sell_ratio(pair),
                                'timestamp': datetime.now()
                            })
                            logger.info(f"Found potential token: {pair.get('baseToken', {}).get('symbol')} at ${float(pair.get('priceUsd', 0)):.6f}")
                        else:
                            logger.debug(f"Token {pair.get('baseToken', {}).get('symbol')} failed check: {reason}")
        except Exception as e:
            logger.error(f"Error scanning new tokens: {e}")

    def _calculate_buy_sell_ratio(self, pair):
        """Calculate buy/sell ratio from pair data"""
        txns_1h = pair.get('txns', {}).get('h1', {})
        buys = txns_1h.get('buys', 0)
        sells = txns_1h.get('sells', 0)
        return buys / sells if sells > 0 else float('inf')

    def get_potential_tokens(self):
        """Return list of potential tokens found"""
        # Clean up old tokens
        current_time = datetime.now()
        self.potential_tokens = [
            token for token in self.potential_tokens
            if (current_time - token['timestamp']).total_seconds() < 3600  # Keep tokens for 1 hour
        ]
        return self.potential_tokens

    async def start_scanning(self):
        """Start continuous token scanning"""
        await self.initialize()
        while True:
            await self.scan_new_tokens()
            await asyncio.sleep(60)  # Scan every minute
