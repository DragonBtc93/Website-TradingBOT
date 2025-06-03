import asyncio
import unittest
from unittest.mock import AsyncMock, patch
import logging
from datetime import datetime, timedelta # Import timedelta

# Make sure aiohttp is imported if specific exceptions like aiohttp.ClientError are used.
import aiohttp

# Assuming config values are directly accessed like: from trading_bot.config import RUGCHECK_SCORE_THRESHOLD
# For testing, it's often better to patch these or set them on the instance if the class uses them via self.
# The scanner.py currently imports them at the module level. To override for tests,
# we would typically patch them in the module where they are used.
# E.g., @patch('trading_bot.scanner.RUGCHECK_SCORE_THRESHOLD', 75)
from trading_bot.scanner import TokenScanner
# For accessing config values that might be used by the scanner module
# from trading_bot import config # Not strictly needed if we patch scanner's direct imports

# Suppress logging for cleaner test output
logging.disable(logging.CRITICAL)

class TestTokenScanner(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.scanner = TokenScanner()
        # It's important that the scanner's session is initialized for some tests
        # We'll handle this per test or ensure initialize is called if session is needed.
        # For verify_token_safety_rugcheck, the session is passed as an argument, which is good.
        # For scan_new_tokens, it uses self.session.

        # Config values are imported at module level in scanner.py.
        # We will use @patch for each test method that requires specific config values
        # to ensure test isolation and correct mocking of these module-level constants.

    async def asyncSetUp(self):
        # Initialize scanner session for tests that might use it internally
        await self.scanner.initialize()

    async def asyncTearDown(self):
        if self.scanner.session:
            await self.scanner.close()

    # --- Tests for verify_token_safety_rugcheck ---

    @patch('trading_bot.scanner.RUGCHECK_SCORE_THRESHOLD', 70)
    @patch('trading_bot.scanner.RUGCHECK_CRITICAL_RISK_NAMES', ["Honeypot", "Rugpull"])
    @patch('aiohttp.ClientSession.get', new_callable=AsyncMock)
    async def test_rugcheck_safe_token(self, mock_get, _mock_crit_names, _mock_score_thresh): # Order of mocks is reversed from decorators
        mock_get.return_value.__aenter__.return_value.status = 200
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(return_value={
            "scoreNormalised": 80,
            "rugged": False,
            "risks": [{"name": "LowLiquidity", "level": "warning", "description": "Liquidity is low"}]
        })
        result = await self.scanner.verify_token_safety_rugcheck(self.scanner.session, "test_safe_token")

        self.assertTrue(result['is_safe'])
        self.assertEqual(result['score_normalised'], 80)
        self.assertEqual(result['api_error'], None)
        self.assertEqual(len(result['reasons']), 0)

    @patch('trading_bot.scanner.RUGCHECK_SCORE_THRESHOLD', 50)
    @patch('aiohttp.ClientSession.get', new_callable=AsyncMock)
    async def test_rugcheck_unsafe_low_score(self, mock_get, _mock_score_thresh):
        mock_get.return_value.__aenter__.return_value.status = 200
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(return_value={
            "scoreNormalised": 30, # Below threshold
            "rugged": False,
            "risks": []
        })
        result = await self.scanner.verify_token_safety_rugcheck(self.scanner.session, "test_low_score_token")

        self.assertFalse(result['is_safe'])
        self.assertIn("Score (30) is below threshold (50)", result['reasons'])

    @patch('trading_bot.scanner.RUGCHECK_CRITICAL_RISK_NAMES', ["Honeypot", "Rugpull"])
    @patch('trading_bot.scanner.RUGCHECK_SCORE_THRESHOLD', 70) # Keep score high to isolate critical risk
    @patch('aiohttp.ClientSession.get', new_callable=AsyncMock)
    async def test_rugcheck_unsafe_critical_risk(self, mock_get, _mock_score_thresh, _mock_crit_names):
        mock_get.return_value.__aenter__.return_value.status = 200
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(return_value={
            "scoreNormalised": 80,
            "rugged": False,
            "risks": [{"name": "Honeypot", "level": "critical", "description": "This is a honeypot!"}]
        })
        result = await self.scanner.verify_token_safety_rugcheck(self.scanner.session, "test_critical_risk_token")

        self.assertFalse(result['is_safe'])
        self.assertTrue(any("Critical risk: Honeypot" in reason for reason in result['reasons']))

    @patch('aiohttp.ClientSession.get', new_callable=AsyncMock)
    async def test_rugcheck_api_error_client_error(self, mock_get):
        mock_get.side_effect = aiohttp.ClientError("API Test Error")
        result = await self.scanner.verify_token_safety_rugcheck(self.scanner.session, "test_api_error_token")

        self.assertFalse(result['is_safe'])
        # The actual error message from scanner.py is "Unexpected error: API Test Error"
        self.assertIn("Unexpected error: API Test Error", result['reasons'])
        self.assertIn("Unexpected error: API Test Error", result['api_error'])


    @patch('aiohttp.ClientSession.get', new_callable=AsyncMock)
    async def test_rugcheck_token_not_found_404(self, mock_get):
        mock_response = mock_get.return_value.__aenter__.return_value
        mock_response.status = 404
        mock_response.text = AsyncMock(return_value="Not Found")
        # raise_for_status() is called in the SUT, so we don't need to mock its side effect here
        # as the status code 404 is handled before raise_for_status in the new SUT logic.

        result = await self.scanner.verify_token_safety_rugcheck(self.scanner.session, "test_404_token")

        self.assertFalse(result['is_safe'])
        self.assertIn("Token not found on RugCheck", result['reasons'])
        self.assertIn("Token not found (404)", result['api_error'])

    # --- Tests for analyze_token_metrics (focus on market cap) ---

    @patch('trading_bot.scanner.TARGET_MARKET_CAP_TO_SCAN', 30000)
    def test_analyze_mcap_below_target(self, _mock_target_mcap):
        mock_token_data = {
            "baseToken": {"symbol": "TEST"}, "pairAddress": "PAIR_XYZ", "fdv": 20000
        }
        passed, reason = self.scanner.analyze_token_metrics(mock_token_data)
        self.assertFalse(passed)
        self.assertIn("MC $20,000 < Target $30,000", reason)

    @patch('trading_bot.scanner.TARGET_MARKET_CAP_TO_SCAN', 30000)
    @patch('trading_bot.scanner.MAX_MARKET_CAP', 750000)
    def test_analyze_mcap_above_max(self, _mock_max_mcap, _mock_target_mcap):
        mock_token_data = {
            "baseToken": {"symbol": "TEST"}, "pairAddress": "PAIR_XYZ", "fdv": 800000
        }
        passed, reason = self.scanner.analyze_token_metrics(mock_token_data)
        self.assertFalse(passed)
        self.assertIn("MC $800,000 > Max $750,000", reason)

    @patch('trading_bot.scanner.TARGET_MARKET_CAP_TO_SCAN', 30000)
    @patch('trading_bot.scanner.MAX_MARKET_CAP', 750000)
    @patch('trading_bot.scanner.MAX_TOKEN_AGE_HOURS', 6) # Example of another config
    @patch('trading_bot.scanner.MIN_LIQUIDITY', 1000)   # Example
    def test_analyze_mcap_in_range_fails_on_next_check(self, _min_liq, _max_age, _max_mcap, _target_mcap):
        mock_token_data = {
            "baseToken": {"symbol": "TEST"}, "pairAddress": "PAIR_XYZ", "fdv": 50000, # MC is fine
            "pairCreatedAt": (datetime.now() - timedelta(hours=10)).timestamp() * 1000, # Too old
            "liquidity": {"usd": "50000"}, # Assume this would pass if age didn't fail
            "txns": {"h1": {"buys": 50, "sells": 50}}, "volume": {"h1": "1000", "h24": "10000"}, "priceChange": {"h1": "1"}
        }
        passed, reason = self.scanner.analyze_token_metrics(mock_token_data)
        self.assertFalse(passed)
        self.assertIn("Token too old", reason)

    # --- Tests for scan_new_tokens (integration - simplified) ---
    @patch('aiohttp.ClientSession.get', new_callable=AsyncMock)
    @patch('trading_bot.scanner.TokenScanner.analyze_token_metrics')
    @patch('trading_bot.scanner.TokenScanner.verify_token_safety_rugcheck', new_callable=AsyncMock)
    async def test_scan_new_tokens_filters_unsafe_rugcheck(self, mock_rugcheck, mock_analyze_metrics, mock_dex_get):
        mock_dex_get.return_value.__aenter__.return_value.status = 200
        mock_dex_get.return_value.__aenter__.return_value.json = AsyncMock(return_value={
            "pairs": [{"baseToken": {"address": "addr1", "symbol": "UNSAFE"}, "pairAddress": "pair1", "dexId": "dex1"}]
        })
        mock_analyze_metrics.return_value = (True, "Passed primary analysis")
        mock_rugcheck.return_value = {"is_safe": False, "reasons": ["Test Unsafe by RugCheck"], "api_error": None}

        await self.scanner.scan_new_tokens()
        self.assertEqual(len(self.scanner.potential_tokens), 0)
        mock_rugcheck.assert_called_once_with(self.scanner.session, "addr1")

    @patch('aiohttp.ClientSession.get', new_callable=AsyncMock)
    @patch('trading_bot.scanner.TokenScanner.analyze_token_metrics')
    @patch('trading_bot.scanner.TokenScanner.verify_token_safety_rugcheck', new_callable=AsyncMock)
    async def test_scan_new_tokens_filters_failed_metrics(self, mock_rugcheck, mock_analyze_metrics, mock_dex_get):
        mock_dex_get.return_value.__aenter__.return_value.status = 200
        mock_dex_get.return_value.__aenter__.return_value.json = AsyncMock(return_value={
             "pairs": [{"baseToken": {"address": "addr2", "symbol": "FAILMETRIC"}, "pairAddress": "pair2", "dexId": "dex2"}]
        })
        mock_analyze_metrics.return_value = (False, "Failed metrics analysis")

        await self.scanner.scan_new_tokens()
        self.assertEqual(len(self.scanner.potential_tokens), 0)
        mock_analyze_metrics.assert_called_once()
        mock_rugcheck.assert_not_called()

    @patch('aiohttp.ClientSession.get', new_callable=AsyncMock)
    @patch('trading_bot.scanner.TokenScanner.analyze_token_metrics')
    @patch('trading_bot.scanner.TokenScanner.verify_token_safety_rugcheck', new_callable=AsyncMock)
    @patch('trading_bot.scanner.TokenScanner.get_social_sentiment_placeholder', new_callable=AsyncMock)
    async def test_scan_new_tokens_adds_valid_token(self, mock_sentiment, mock_rugcheck, mock_analyze_metrics, mock_dex_get):
        test_token_addr, test_token_sym, test_pair_addr = "addr_safe", "SAFE", "pair_safe"
        mock_dex_pair_data = {
            "baseToken": {"address": test_token_addr, "symbol": test_token_sym},
            "pairAddress": test_pair_addr, "dexId": "dex_s", "priceUsd": "1", "fdv": "50000",
            "liquidity": {"usd": "60000"}, "volume": {"h24": "10000"},
            # Add other fields to ensure analyze_token_metrics passes
            "pairCreatedAt": (datetime.now() - timedelta(hours=1)).timestamp() * 1000,
            "txns": {"h1": {"buys": 100, "sells": 10}}, "priceChange": {"h1": "5"},
             "holders": {"total": 200}
        }
        mock_dex_get.return_value.__aenter__.return_value.status = 200
        mock_dex_get.return_value.__aenter__.return_value.json = AsyncMock(return_value={"pairs": [mock_dex_pair_data]})

        mock_analyze_metrics.return_value = (True, "Passed primary analysis")
        mock_rugcheck_assessment = {"is_safe": True, "score_normalised": 90, "reasons": [], "api_error": None}
        mock_rugcheck.return_value = mock_rugcheck_assessment
        mock_sentiment.return_value = {"sentiment_score": 0.7, "sentiment": "positive"}

        # Patch all relevant config values for this specific test's call to analyze_token_metrics
        with patch('trading_bot.scanner.TARGET_MARKET_CAP_TO_SCAN', 30000), \
             patch('trading_bot.scanner.MAX_MARKET_CAP', 750000), \
             patch('trading_bot.scanner.MAX_TOKEN_AGE_HOURS', 24), \
             patch('trading_bot.scanner.MIN_LIQUIDITY', 50000), \
             patch('trading_bot.scanner.MIN_TRANSACTIONS', 50), \
             patch('trading_bot.scanner.MIN_BUY_SELL_RATIO', 0.1), \
             patch('trading_bot.scanner.VOLUME_SPIKE_THRESHOLD', 0.1), \
             patch('trading_bot.scanner.MIN_HOLDER_COUNT', 100):
            await self.scanner.scan_new_tokens()

        self.assertEqual(len(self.scanner.potential_tokens), 1)
        added_token = self.scanner.potential_tokens[0]
        self.assertEqual(added_token['address'], test_token_addr)
        self.assertEqual(added_token['rugcheck_assessment'], mock_rugcheck_assessment)
        self.assertIn('social_sentiment', added_token)

if __name__ == '__main__':
    unittest.main()

```
