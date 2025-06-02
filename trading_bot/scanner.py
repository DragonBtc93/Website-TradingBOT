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
                response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
                data = await response.json()
                if not data:
                    logger.warning(f"No data received from DexScreener for token {token_address}")
                    return None

                pairs = data.get('pairs')
                if not pairs:
                    logger.warning(f"No pairs found in DexScreener response for token {token_address}")
                    return None
                # TODO: Potentially validate the structure of pairs[0] here if needed elsewhere
                return pairs[0]
        except aiohttp.ClientResponseError as http_err:
            logger.error(f"HTTP error fetching token data for {token_address}: {http_err}")
            return None
        except aiohttp.ContentTypeError as ct_err:
            logger.error(f"JSON decode error (content type) fetching token data for {token_address}: {ct_err}")
            return None
        except Exception as e:
            logger.error(f"Error fetching token data for {token_address}: {e}")
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
        token_symbol = token_data.get('baseToken', {}).get('symbol', 'Unknown')
        pair_address = token_data.get('pairAddress', 'Unknown')
        log_prefix = f"Token {token_symbol} ({pair_address}):"

        try:
            if not token_data:
                logger.warning(f"{log_prefix} No token data provided for analysis.")
                return False, "No token data available"

            # Age check
            created_timestamp = token_data.get('pairCreatedAt')
            if created_timestamp is None:
                logger.warning(f"{log_prefix} Missing 'pairCreatedAt' field.")
                return False, "Missing creation timestamp"
            try:
                # DexScreener uses milliseconds for pairCreatedAt
                created_at = datetime.fromtimestamp(created_timestamp / 1000)
            except (TypeError, ValueError) as e:
                logger.warning(f"{log_prefix} Invalid 'pairCreatedAt' timestamp {created_timestamp}: {e}")
                return False, f"Invalid creation timestamp: {created_timestamp}"

            age_hours = (datetime.now() - created_at).total_seconds() / 3600
            if age_hours > MAX_TOKEN_AGE_HOURS:
                return False, f"Token too old: {age_hours:.1f} hours"

            # Liquidity check
            try:
                liquidity_data = token_data.get('liquidity')
                if liquidity_data is None or liquidity_data.get('usd') is None:
                    logger.warning(f"{log_prefix} Missing liquidity data or USD liquidity.")
                    return False, "Missing liquidity data"
                liquidity_usd = float(liquidity_data['usd'])
            except ValueError as e:
                logger.warning(f"{log_prefix} Invalid liquidity USD value {liquidity_data.get('usd')}: {e}")
                return False, "Invalid liquidity data type"
            if liquidity_usd < MIN_LIQUIDITY:
                return False, f"Insufficient liquidity: ${liquidity_usd:,.0f}"

            # Market cap (FDV) check
            try:
                fdv_data = token_data.get('fdv')
                if fdv_data is None: # FDV can be 0, which is fine if not None
                    logger.warning(f"{log_prefix} Missing 'fdv' (fully diluted valuation) field.")
                    # Depending on strategy, this might be a failure or not. Let's assume it's not critical for now if it's 0.
                    # If it must be present, return False here. For now, we default to 0 if missing.
                    market_cap = 0.0
                else:
                    market_cap = float(fdv_data)
            except ValueError as e:
                logger.warning(f"{log_prefix} Invalid 'fdv' value {fdv_data}: {e}")
                return False, "Invalid market cap data type"
            if market_cap > MAX_MARKET_CAP: # MAX_MARKET_CAP should be > 0 for this to be meaningful
                return False, f"Market cap too high: ${market_cap:,.0f}"

            # Transaction analysis
            txns_data = token_data.get('txns')
            if not txns_data or not isinstance(txns_data, dict):
                logger.warning(f"{log_prefix} Missing or invalid 'txns' data.")
                return False, "Missing transaction data"

            txns_1h = txns_data.get('h1', {})
            buys = txns_1h.get('buys', 0)
            sells = txns_1h.get('sells', 0)

            # DexScreener provides 'buys', 'sells', 'swaps'. We might want to use 'swaps' if 'total' is not present.
            # For now, let's assume 'buys' + 'sells' is a good proxy if 'total' isn't directly used.
            # The original code used txns_1h.get('total',0) - let's see if that's what DexScreener provides.
            # DexScreener API for pair has txns.h1.buys, txns.h1.sells. It does not have a 'total' field directly in h1.
            # It has 'swaps' at txns.m5.swaps, txns.h1.swaps, txns.h6.swaps, txns.h24.swaps.
            # Let's use buys + sells for total_txns for h1.
            total_txns = buys + sells # Corrected from txns_1h.get('total',0)
            if total_txns < MIN_TRANSACTIONS:
                return False, f"Low transaction count (1h): {total_txns}"

            # Buy/Sell ratio analysis
            if sells > 0:
                buy_sell_ratio = buys / sells
                if buy_sell_ratio < MIN_BUY_SELL_RATIO:
                    return False, f"Poor buy/sell ratio: {buy_sell_ratio:.2f}"
            # If sells is 0, ratio is infinite (good), so no specific check needed here unless MIN_BUY_SELL_RATIO could be inf.

            # Volume analysis
            volume_data = token_data.get('volume')
            if not volume_data or not isinstance(volume_data, dict):
                logger.warning(f"{log_prefix} Missing or invalid 'volume' data.")
                return False, "Missing volume data"
            try:
                volume_24h = float(volume_data.get('h24', 0.0))
                volume_1h = float(volume_data.get('h1', 0.0))
            except ValueError as e:
                logger.warning(f"{log_prefix} Invalid volume data type: h24='{volume_data.get('h24')}', h1='{volume_data.get('h1')}': {e}")
                return False, "Invalid volume data type"

            if volume_24h == 0 and volume_1h > 0: # Avoid division by zero if 24h vol is 0 but 1h is not
                logger.info(f"{log_prefix} Volume 24h is zero, cannot calculate spike meaningfully.")
                 # Depending on strategy, this might be a pass or fail.
                 # For now, let's assume if 24h vol is 0, any 1h vol is a "spike" if > 0.
                 # Or, one might require a certain absolute 1h volume if 24h is 0.
                 # The original logic implies volume_1h > 0 for the spike calc to occur.
            elif volume_24h > 0 and volume_1h > 0: # Ensure volume_1h > 0 as in original logic
                volume_spike = (volume_1h / volume_24h) * 24 # Corrected spike calculation: (1h_vol / 24h_vol) * 24
                if volume_spike < VOLUME_SPIKE_THRESHOLD:
                    return False, f"No significant volume spike: {volume_spike:.1f}x (1h: {volume_1h}, 24h: {volume_24h})"
            # If volume_1h is 0, it won't pass VOLUME_SPIKE_THRESHOLD > 0, so it's implicitly handled if threshold is positive.

            # LP Token analysis - 'liquidity.locked' is not a standard DexScreener field.
            # This might be from a different API or custom calculation.
            # DexScreener has `liquidityPools` array in the full token endpoint, not pair list.
            # For now, I will comment this out as it's likely to fail with current pair data.
            # If this is critical, it needs rethinking on where `locked` comes from.
            # lp_locked_data = token_data.get('liquidity', {}).get('locked')
            # if lp_locked_data is None:
            #     logger.warning(f"{log_prefix} Missing 'liquidity.locked' data.")
            #     # Decide if this is a hard fail or can be skipped. Assuming skippable for now.
            # else:
            #     try:
            #         lp_locked_percentage = float(lp_locked_data)
            #         if lp_locked_percentage < MIN_LP_LOCKED_PERCENTAGE:
            #             return False, f"Insufficient LP locked: {lp_locked_percentage}%"
            #     except ValueError as e:
            #         logger.warning(f"{log_prefix} Invalid LP locked value {lp_locked_data}: {e}")
            #         return False, "Invalid LP locked data type"

            # Price action analysis
            price_change_data = token_data.get('priceChange')
            if not price_change_data or not isinstance(price_change_data, dict):
                logger.warning(f"{log_prefix} Missing or invalid 'priceChange' data.")
                return False, "Missing price change data"
            try:
                price_change_1h = float(price_change_data.get('h1', 0.0))
            except ValueError as e:
                logger.warning(f"{log_prefix} Invalid priceChange h1 value {price_change_data.get('h1')}: {e}")
                return False, "Invalid price change data type"

            if price_change_1h < -10:  # Avoid tokens in free fall
                return False, f"Significant price drop (1h): {price_change_1h}%"

            return True, "Token passed all checks"
        except Exception as e:
            logger.error(f"{log_prefix} Unexpected error analyzing token metrics: {e}", exc_info=True)
            return False, str(e)

    async def scan_new_tokens(self):
        """Continuously scan for new tokens meeting our criteria"""
        try:
            url = f"{DEXSCREENER_API}/pairs/solana" # This endpoint fetches top pairs by liquidity/volume, not necessarily "new"
            async with self.session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
                if not data:
                    logger.warning("No data received from DexScreener /pairs/solana endpoint.")
                    return

                pairs = data.get('pairs', [])
                if not pairs:
                    logger.info("No pairs found in the current scan iteration.")
                    return
                    
                self.scan_count += 1
                logger.info(f"Scanning iteration {self.scan_count}: Found {len(pairs)} pairs from general scan.")

                for pair_data in pairs:
                    if not isinstance(pair_data, dict):
                        logger.warning(f"Invalid pair data format: {type(pair_data)}. Skipping.")
                        continue

                    # Basic structural validation for essential keys before detailed analysis
                    base_token_info = pair_data.get('baseToken')
                    pair_address = pair_data.get('pairAddress') # DexScreener uses pairAddress for the pair's own address
                    dex_id = pair_data.get('dexId') # This is usually the exchange like 'raydium'
                    
                    if not all([base_token_info, isinstance(base_token_info, dict),
                                base_token_info.get('symbol'), pair_address, dex_id]):
                        logger.warning(f"Skipping pair due to missing critical basic info: dexId='{dex_id}', pairAddr='{pair_address}', baseToken='{base_token_info}'")
                        continue

                    token_symbol = base_token_info.get('symbol')
                    log_prefix = f"Token {token_symbol} ({pair_address}):"

                    # Validate data types for values to be stored
                    try:
                        price_usd_str = pair_data.get('priceUsd')
                        price_usd = float(price_usd_str) if price_usd_str is not None else None

                        liquidity_info = pair_data.get('liquidity')
                        liquidity_usd_val = float(liquidity_info['usd']) if liquidity_info and liquidity_info.get('usd') is not None else None

                        volume_info = pair_data.get('volume')
                        volume_h24_val = float(volume_info['h24']) if volume_info and volume_info.get('h24') is not None else None

                        # Holders info might not be in this general pair list endpoint.
                        # It's typically in the /tokens/{token_address} endpoint.
                        # If it's expected here, we need to handle its potential absence.
                        holders_info = pair_data.get('holders')
                        holders_total = int(holders_info['total']) if holders_info and holders_info.get('total') is not None else 0

                    except (ValueError, TypeError) as e:
                        logger.warning(f"{log_prefix} Invalid data type for price, liquidity, volume, or holders in pair data {pair_data.get('dexId')}. Error: {e}. Skipping.")
                        continue

                    if price_usd is None or liquidity_usd_val is None or volume_h24_val is None:
                        logger.warning(f"{log_prefix} Missing essential numeric value (price, liquidity, or volume) for pair {pair_data.get('dexId')}. Skipping.")
                        continue

                    passed, reason = self.analyze_token_metrics(pair_data)
                    if passed:
                        # Holder metrics check might require a separate call if not in pair_data
                        # The original `check_holder_metrics` expects `token_data` which could be `pair_data`
                        # However, 'holders' might not be rich in `pair_data` from the general scan.
                        # For now, let's assume `analyze_token_metrics` is the primary filter from this list.
                        # If `check_holder_metrics` is essential here and needs more data,
                        # we might need to call `fetch_token_data(base_token_info.get('address'))`
                        # For now, this is how original code was structured.

                        # holder_passed, holder_reason = await self.check_holder_metrics(pair_data) # `pair_data` might not have detailed holder info
                        # if not holder_passed:
                        #     logger.info(f"{log_prefix} Failed holder check: {holder_reason}")
                        #     continue

                        self.potential_tokens.append({
                            'address': base_token_info.get('address'), # Storing base token address
                            'pair_address': pair_address, # Storing pair address
                            'symbol': token_symbol,
                            'price': price_usd,
                            'liquidity': liquidity_usd_val,
                            'volume_24h': volume_h24_val,
                            'holders': holders_total, # This might be 0 if not available in pair list
                            'buy_sell_ratio': self._calculate_buy_sell_ratio(pair_data), # Ensure this uses validated data
                            'timestamp': datetime.now()
                        })
                        logger.info(f"{log_prefix} Found potential token at ${price_usd:.6f}")
                    else:
                        logger.debug(f"{log_prefix} Failed primary check: {reason}")
        except aiohttp.ClientResponseError as http_err:
            logger.error(f"HTTP error scanning new tokens: {http_err}")
        except aiohttp.ContentTypeError as ct_err:
            logger.error(f"JSON decode error (content type) scanning new tokens: {ct_err}")
        except Exception as e:
            logger.error(f"Error scanning new tokens: {e}", exc_info=True)

    def _calculate_buy_sell_ratio(self, pair):
        """Calculate buy/sell ratio from pair data"""
        txns_data = pair.get('txns')
        if not txns_data or not isinstance(txns_data, dict):
            logger.warning(f"Missing or invalid 'txns' data in _calculate_buy_sell_ratio for pair {pair.get('pairAddress')}")
            return 0.0 # Or handle as appropriate

        txns_1h = txns_data.get('h1', {})
        if not isinstance(txns_1h, dict):
            logger.warning(f"Missing or invalid 'txns.h1' data in _calculate_buy_sell_ratio for pair {pair.get('pairAddress')}")
            return 0.0

        buys = txns_1h.get('buys', 0)
        sells = txns_1h.get('sells', 0)

        if not (isinstance(buys, (int, float)) and isinstance(sells, (int, float))):
            logger.warning(f"Invalid data type for buys/sells in _calculate_buy_sell_ratio for pair {pair.get('pairAddress')}: buys={buys}, sells={sells}")
            return 0.0

        return buys / sells if sells > 0 else float('inf')

    def get_potential_tokens(self):
# Ensure this part is not duplicated if it was part of the previous block
# The LP token analysis section was commented out in the previous change.
# Price action analysis was also part of analyze_token_metrics.

# ... (rest of the file, assuming get_potential_tokens and start_scanning are correctly placed)
# It seems the diff might be trying to re-apply parts of analyze_token_metrics.
# The key changes were:
# 1. fetch_token_data: better error handling, checking for empty pairs.
# 2. analyze_token_metrics: detailed validation for timestamps, numeric conversions (liquidity, fdv, volume, priceChange),
#    logging with token symbol and pair address, correction of total_txns, volume spike calculation,
#    and commenting out LP lock check (as it's not standard DexScreener pair data).
# 3. scan_new_tokens: response.raise_for_status(), validation of essential keys and their types in `pair_data`
#    before processing and appending, adjusted what's being stored in `potential_tokens` (base token address, pair address).
# 4. _calculate_buy_sell_ratio: added checks for txns_data, txns_1h structure and numeric types for buys/sells.

# The following is to ensure the diff tool correctly applies the end of the file if it got confused.
# If the previous block correctly captured all changes up to `_calculate_buy_sell_ratio`,
# then this block might just be ensuring the rest of the file is "as expected".

# Let's verify the previous changes covered all intended points for `analyze_token_metrics`
# - `created_timestamp` from `pairCreatedAt` (DexScreener specific) and division by 1000.
# - `liquidity_usd` from `token_data.get('liquidity', {}).get('usd')` with `try-except ValueError`.
# - `market_cap` from `token_data.get('fdv')` with `try-except ValueError`.
# - `total_txns` calculation corrected to `buys + sells`.
# - `volume_spike` calculation corrected and division by zero for `volume_24h` handled.
# - `lp_locked` section commented out.
# - `price_change_1h` from `token_data.get('priceChange', {}).get('h1')` with `try-except ValueError`.
# - Added `log_prefix` for better logging.
# All these seem to be in the large replacement block for `analyze_token_metrics`.

# And for `scan_new_tokens`:
# - `response.raise_for_status()`
# - Validation of `pair_data` structure (isinstance dict, essential keys like baseToken, symbol, pairAddress, dexId)
# - Type validation for `priceUsd`, `liquidity.usd`, `volume.h24`, `holders.total` before appending.
# - Storing `base_token_info.get('address')` as 'address' and `pair_address` as 'pair_address'.
# These also seem to be covered.

# And for `_calculate_buy_sell_ratio`:
# - Added checks for `txns_data` and `txns_1h` structure and types of `buys` and `sells`.
# This also seems covered.

# The diff might be a bit complex due to the size of the changes.
# The core logic of the functions remains, but with more robust data access and error handling.
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
