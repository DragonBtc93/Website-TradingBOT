import asyncio
import logging
from datetime import datetime, timedelta
import aiohttp
import pandas as pd
# Import necessary config variables explicitly for clarity and correctness
from .config import (
    DEXSCREENER_API, TARGET_MARKET_CAP_TO_SCAN, MAX_MARKET_CAP, MAX_TOKEN_AGE_HOURS,
    MIN_LIQUIDITY, MIN_TRANSACTIONS, MIN_BUY_SELL_RATIO, VOLUME_SPIKE_THRESHOLD,
    MIN_HOLDER_COUNT,
    RUGCHECK_API_ENDPOINT, RUGCHECK_API_KEY,
    RUGCHECK_SCORE_THRESHOLD, RUGCHECK_CRITICAL_RISK_NAMES
)


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
                response.raise_for_status()
                data = await response.json()
                if not data or not data.get('pairs'):
                    logger.warning(f"No pairs data in DexScreener response for token {token_address}")
                    return None
                return data['pairs'][0]
        except Exception as e:
            logger.error(f"Error fetching token data for {token_address}: {e}", exc_info=True)
            return None

    async def check_holder_metrics(self, token_data):
        """Analyze holder metrics (basic)"""
        token_symbol = token_data.get('baseToken', {}).get('symbol', 'Unknown')
        log_prefix = f"Token {token_symbol} Holder Check:"
        try:
            holders_data = token_data.get('holders', {})
            if not holders_data:
                logger.debug(f"{log_prefix} No 'holders' data in provided token_data.")
                return True, "Holder data not available"
            total_holders = holders_data.get('total', 0)
            if total_holders < MIN_HOLDER_COUNT:
                return False, f"Insufficient holders: {total_holders} < {MIN_HOLDER_COUNT}"
            logger.debug(f"{log_prefix} Holder count {total_holders} meets minimum.")
            return True, "Holder metrics (basic count) passed"
        except Exception as e:
            logger.error(f"{log_prefix} Error: {e}", exc_info=True)
            return False, str(e)

    def analyze_token_metrics(self, token_data):
        """Analyze token metrics based on our criteria"""
        token_symbol = token_data.get('baseToken', {}).get('symbol', 'Unknown')
        pair_address = token_data.get('pairAddress', 'Unknown')
        log_prefix = f"Token {token_symbol} ({pair_address}):"

        try:
            if not token_data:
                return False, "No token data"

            fdv_data = token_data.get('fdv')
            if fdv_data is None: return False, "Missing FDV (market cap)"
            try: market_cap = float(fdv_data)
            except (ValueError, TypeError): return False, "Invalid FDV data type"

            if market_cap < TARGET_MARKET_CAP_TO_SCAN:
                return False, f"MC ${market_cap:,.0f} < Target ${TARGET_MARKET_CAP_TO_SCAN:,.0f}"
            if market_cap > MAX_MARKET_CAP:
                return False, f"MC ${market_cap:,.0f} > Max ${MAX_MARKET_CAP:,.0f}"
            logger.info(f"{log_prefix} MC Passed: Target ${TARGET_MARKET_CAP_TO_SCAN:,.0f} <= Actual ${market_cap:,.0f} <= Max ${MAX_MARKET_CAP:,.0f}")

            created_timestamp = token_data.get('pairCreatedAt')
            if created_timestamp is None: return False, "Missing pairCreatedAt"
            try: created_at = datetime.fromtimestamp(created_timestamp / 1000)
            except (TypeError, ValueError): return False, "Invalid pairCreatedAt timestamp"
            age_hours = (datetime.now() - created_at).total_seconds() / 3600
            if age_hours > MAX_TOKEN_AGE_HOURS:
                return False, f"Token too old: {age_hours:.1f}h > {MAX_TOKEN_AGE_HOURS}h"

            liquidity_data = token_data.get('liquidity')
            if not liquidity_data or liquidity_data.get('usd') is None: return False, "Missing liquidity USD"
            try: liquidity_usd = float(liquidity_data['usd'])
            except ValueError: return False, "Invalid liquidity USD type"
            if liquidity_usd < MIN_LIQUIDITY:
                return False, f"Liquidity ${liquidity_usd:,.0f} < Min ${MIN_LIQUIDITY:,.0f}"

            txns_data = token_data.get('txns', {}).get('h1', {})
            buys, sells = txns_data.get('buys', 0), txns_data.get('sells', 0)
            if (buys + sells) < MIN_TRANSACTIONS:
                return False, f"Txns (1h) {buys+sells} < Min {MIN_TRANSACTIONS}"
            if sells > 0 and (buys / sells) < MIN_BUY_SELL_RATIO:
                return False, f"Buy/Sell ratio {(buys/sells):.2f} < Min {MIN_BUY_SELL_RATIO}"

            volume_data = token_data.get('volume', {})
            try:
                volume_1h = float(volume_data.get('h1', 0.0))
                volume_24h = float(volume_data.get('h24', 0.0))
            except ValueError: return False, "Invalid volume data type"
            if volume_24h > 0 and volume_1h > 0 and (volume_1h / volume_24h * 24) < VOLUME_SPIKE_THRESHOLD:
                return False, f"No volume spike: {(volume_1h / volume_24h * 24):.1f}x < {VOLUME_SPIKE_THRESHOLD}x"
            elif volume_1h == 0 and VOLUME_SPIKE_THRESHOLD > 0 : # No 1h volume is not a spike
                 return False, "No 1h volume for spike calc"


            price_change_1h = float(token_data.get('priceChange', {}).get('h1', 0.0))
            if price_change_1h < -10:
                return False, f"Price drop (1h): {price_change_1h}%"

            return True, "Token passed primary checks"
        except Exception as e:
            logger.error(f"{log_prefix} Error in analyze_token_metrics: {e}", exc_info=True)
            return False, str(e)

    async def scan_new_tokens(self):
        """Continuously scan for new tokens meeting our criteria"""
        try:
            url = f"{DEXSCREENER_API}/pairs/solana" # Dexscreener new pairs endpoint
            async with self.session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
                pairs = data.get('pairs', [])
                self.scan_count += 1
                logger.info(f"Scan Iteration {self.scan_count}: Found {len(pairs)} pairs.")

                for pair_data in pairs:
                    base_token_info = pair_data.get('baseToken')
                    if not base_token_info or not base_token_info.get('address') or not base_token_info.get('symbol'):
                        logger.debug("Skipping pair due to missing base token info, address, or symbol.")
                        continue

                    base_token_address = base_token_info['address']
                    token_symbol = base_token_info['symbol']
                    pair_address = pair_data.get('pairAddress', 'N/A')
                    log_prefix = f"Token {token_symbol} ({pair_address}, Mint: {base_token_address}):"

                    passed_primary_checks, reason = self.analyze_token_metrics(pair_data)
                    if not passed_primary_checks:
                        logger.debug(f"{log_prefix} Failed primary checks: {reason}")
                        continue

                    # RugCheck Assessment
                    if not self.session or self.session.closed: await self.initialize() # Ensure session

                    rugcheck_assessment = await self.verify_token_safety_rugcheck(self.session, base_token_address)

                    log_score_norm = rugcheck_assessment.get('score_normalised', 'N/A')
                    logger.info(f"{log_prefix} RugCheck: Safe={rugcheck_assessment.get('is_safe')}, ScoreNorm={log_score_norm}, Reasons={'; '.join(rugcheck_assessment.get('reasons',[])) if rugcheck_assessment.get('reasons') else 'N/A'}, APIError='{rugcheck_assessment.get('api_error')}'")

                    if not rugcheck_assessment.get('is_safe', False):
                        logger.info(f"{log_prefix} Filtered out by RugCheck. Reasons: {'; '.join(rugcheck_assessment.get('reasons', ['No specific reasons given']))}")
                        continue

                    logger.info(f"{log_prefix} Passed RugCheck safety screen.")

                    # Social Sentiment (Placeholder)
                    social_sentiment_data = await self.get_social_sentiment_placeholder(self.session, token_symbol, base_token_address)
                    logger.info(f"{log_prefix} Sentiment (Placeholder): Score='{social_sentiment_data.get('sentiment_score', 'N/A')}', Label='{social_sentiment_data.get('sentiment', 'N/A')}'")

                    # Prepare data for potential_tokens list
                    try:
                        price_usd = float(pair_data.get('priceUsd'))
                        liquidity_usd_val = float(pair_data.get('liquidity', {}).get('usd'))
                        volume_h24_val = float(pair_data.get('volume', {}).get('h24'))
                        holders_total = int(pair_data.get('holders', {}).get('total', 0))
                    except (TypeError, ValueError) as e:
                        logger.warning(f"{log_prefix} Error parsing numeric data for potential token list: {e}. Skipping.")
                        continue

                    self.potential_tokens.append({
                        'address': base_token_address,
                        'pair_address': pair_address,
                        'symbol': token_symbol,
                        'price': price_usd,
                        'liquidity': liquidity_usd_val,
                        'volume_24h': volume_h24_val,
                        'holders': holders_total,
                        'buy_sell_ratio': self._calculate_buy_sell_ratio(pair_data),
                        'timestamp': datetime.now(),
                        'rugcheck_assessment': rugcheck_assessment,
                        'social_sentiment': social_sentiment_data
                    })
                    logger.info(f"{log_prefix} Added to potential tokens. Price: ${price_usd:.6f}")

        except Exception as e:
            logger.error(f"Error in scan_new_tokens loop: {e}", exc_info=True)

    def _calculate_buy_sell_ratio(self, pair):
        txns_1h = pair.get('txns', {}).get('h1', {})
        buys, sells = txns_1h.get('buys', 0), txns_1h.get('sells', 0)
        if not (isinstance(buys, (int, float)) and isinstance(sells, (int, float))): return 0.0
        return buys / sells if sells > 0 else float('inf')

    async def verify_token_safety_rugcheck(self, session: aiohttp.ClientSession, token_address: str) -> dict:
        """
        Verifies token safety using the RugCheck.xyz API endpoint (/v1/tokens/{id}/report/summary).
        Uses configuration from config.py for API endpoint, score thresholds, and critical risk names.
        """
        url = f"{RUGCHECK_API_ENDPOINT}/{token_address}/report/summary"
        headers = {"Content-Type": "application/json"}
        if RUGCHECK_API_KEY:
            headers["X-API-Key"] = RUGCHECK_API_KEY # Corrected header based on typical usage
            logger.debug(f"Using RugCheck API Key for request to {url}")
        else:
            logger.debug(f"No RugCheck API Key for {url}. Proceeding without authentication.")

        default_result = lambda reasons_list, err_msg: {
            'is_safe': False, 'score': None, 'score_normalised': None,
            'risks': [], 'reasons': reasons_list, 'api_error': err_msg
        }

        if not token_address:
            return default_result(['No token address provided.'], 'No token address provided.')

        logger.info(f"Querying RugCheck summary for {token_address}")
        try:
            async with session.get(url, headers=headers, timeout=20) as response:
                raw_response_text = await response.text()
                status_code = response.status

                if status_code == 404: return default_result(['Token not found on RugCheck'], f'Token not found ({status_code})')
                if status_code in [401, 403]: return default_result(['RugCheck API authorization failed'], f'Auth error ({status_code})')
                if status_code == 429: return default_result(['RugCheck API rate limit exceeded'], f'Rate limit ({status_code})')
                response.raise_for_status() # For other 4xx/5xx errors

                response_data = await response.json(content_type=None)
                if not isinstance(response_data, dict):
                    return default_result(['Empty/invalid response from RugCheck'], 'Invalid API response format')

                is_safe = True; reasons = []
                score = response_data.get('score')
                score_normalised = response_data.get('scoreNormalised') # API uses 'scoreNormalised'
                api_risks = response_data.get('risks', [])

                # Score check (RUGCHECK_SCORE_THRESHOLD is min acceptable, higher is better for score_normalised)
                check_val = score_normalised if score_normalised is not None else score
                if check_val is None:
                    is_safe = False; reasons.append("Score missing")
                elif not isinstance(check_val, (int, float)):
                    is_safe = False; reasons.append(f"Score '{check_val}' not numeric")
                elif check_val < RUGCHECK_SCORE_THRESHOLD:
                    is_safe = False; reasons.append(f"Score {check_val} < threshold {RUGCHECK_SCORE_THRESHOLD}")

                # Critical risks check
                if isinstance(api_risks, list):
                    for risk in api_risks:
                        if risk.get('name') in RUGCHECK_CRITICAL_RISK_NAMES:
                            is_safe = False; reasons.append(f"Critical risk: {risk.get('name')} - {risk.get('description','N/A')}")
                else:
                    reasons.append("'risks' field invalid/missing"); # is_safe not changed for this alone, score might still be good

                return {
                    'is_safe': is_safe, 'score': score, 'score_normalised': score_normalised,
                    'risks': api_risks, 'reasons': reasons, 'api_error': None
                }
        except aiohttp.ClientResponseError as e: return default_result([f"HTTP error: {e.status}"], str(e))
        except asyncio.TimeoutError: return default_result(["API call timed out"], "Timeout")
        except aiohttp.ContentTypeError as e: return default_result(["JSON decode error"], str(e))
        except Exception as e:
            logger.error(f"Unexpected error in verify_token_safety_rugcheck for {token_address}: {e}", exc_info=True)
            return default_result([f"Unexpected error: {str(e)}"], str(e))

    async def get_social_sentiment_placeholder(self, session: aiohttp.ClientSession, token_symbol: str, token_address: str) -> dict:
        """
        Placeholder: Simulates fetching social sentiment for a token.
        (Docstring and implementation remain as per previous successful application)
        """
        await asyncio.sleep(0.1)
        logger.debug(f"Simulating social sentiment check for {token_symbol} ({token_address})")
        return {
            'sentiment_score': 0.5, 'sentiment': 'neutral',
            'posts_analyzed': 0, 'source': 'placeholder'
        }

    def get_potential_tokens(self):
        current_time = datetime.now()
        self.potential_tokens = [
            token for token in self.potential_tokens
            if (current_time - token['timestamp']).total_seconds() < 3600
        ]
        return self.potential_tokens

    async def start_scanning(self):
        await self.initialize()
        while True:
            await self.scan_new_tokens()
            await asyncio.sleep(60)
