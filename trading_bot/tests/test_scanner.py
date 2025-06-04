import asyncio
import unittest
from unittest.mock import AsyncMock, patch
import logging
from datetime import datetime, timedelta

import aiohttp

from trading_bot.scanner import TokenScanner
from trading_bot.auth_utils import get_rugcheck_jwt # For mocking
# Import config names that will be patched at the module level of scanner
from trading_bot.config import (
    RUGCHECK_API_ENDPOINT, # Used by scanner, might be good to see its default
    STATIC_RUGCHECK_API_KEY_OR_JWT, # This is what scanner imports
    RUGCHECK_AUTH_SOLANA_PRIVATE_KEY,
    RUGCHECK_AUTH_WALLET_PUBLIC_KEY,
    RUGCHECK_SCORE_THRESHOLD,
    RUGCHECK_CRITICAL_RISK_NAMES,
    TARGET_MARKET_CAP_TO_SCAN,
    MAX_MARKET_CAP,
    MAX_TOKEN_AGE_HOURS,
    MIN_LIQUIDITY,
    MIN_TRANSACTIONS,
    MIN_BUY_SELL_RATIO,
    VOLUME_SPIKE_THRESHOLD,
    MIN_HOLDER_COUNT
)

logging.disable(logging.CRITICAL) # Suppress logging for cleaner test output

class TestTokenScanner(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # This setUp runs before each test method.
        # We create a new scanner instance for each test to ensure isolation.
        self.scanner = TokenScanner()
        # Initializing these here ensures they are reset for each test,
        # especially important if tests modify them via initialize() or _ensure_rugcheck_jwt()
        self.scanner.rugcheck_jwt = None
        self.scanner.rugcheck_jwt_generation_attempted = False


    async def asyncSetUp(self):
        # This runs after setUp for each test.
        # Initialize scanner's aiohttp session.
        # _ensure_rugcheck_jwt is called within initialize, so JWT logic will run here.
        # For tests specifically targeting _ensure_rugcheck_jwt, we might re-call initialize
        # or call _ensure_rugcheck_jwt directly after patching configs.
        # For most other tests, this initial call to initialize() is fine.
        if not self.scanner.session or self.scanner.session.closed:
            await self.scanner.initialize() # This will also call _ensure_rugcheck_jwt

    async def asyncTearDown(self):
        if self.scanner.session:
            await self.scanner.close()

    # --- Tests for _ensure_rugcheck_jwt (tested via initialize) ---

    @patch('trading_bot.scanner.get_rugcheck_jwt', new_callable=AsyncMock)
    async def test_ensure_jwt_uses_static_if_present_and_no_dynamic_keys(self, mock_auth_get_jwt):
        with patch('trading_bot.scanner.STATIC_RUGCHECK_API_KEY_OR_JWT', "static_jwt_token"), \
             patch('trading_bot.scanner.RUGCHECK_AUTH_SOLANA_PRIVATE_KEY', None), \
             patch('trading_bot.scanner.RUGCHECK_AUTH_WALLET_PUBLIC_KEY', None):

            # Re-initialize scanner with patched config for this test's scope
            current_scanner = TokenScanner() # New instance to pick up patched static JWT
            await current_scanner.initialize() # Calls _ensure_rugcheck_jwt

            self.assertEqual(current_scanner.rugcheck_jwt, "static_jwt_token")
            mock_auth_get_jwt.assert_not_called()
            await current_scanner.close()


    @patch('trading_bot.scanner.get_rugcheck_jwt', new_callable=AsyncMock)
    async def test_ensure_jwt_generates_dynamically_overwrites_static(self, mock_auth_get_jwt):
        with patch('trading_bot.scanner.STATIC_RUGCHECK_API_KEY_OR_JWT', "old_static_jwt"), \
             patch('trading_bot.scanner.RUGCHECK_AUTH_SOLANA_PRIVATE_KEY', "test_priv_key_hex_seed"), \
             patch('trading_bot.scanner.RUGCHECK_AUTH_WALLET_PUBLIC_KEY', "test_pub_key_address"):

            mock_auth_get_jwt.return_value = "generated_dynamic_jwt"

            current_scanner = TokenScanner() # New instance
            await current_scanner.initialize()

            self.assertEqual(current_scanner.rugcheck_jwt, "generated_dynamic_jwt")
            mock_auth_get_jwt.assert_called_once_with(
                current_scanner.session, # or a temp session if main one was closed
                "test_priv_key_hex_seed",
                "test_pub_key_address"
            )
            await current_scanner.close()

    @patch('trading_bot.scanner.get_rugcheck_jwt', new_callable=AsyncMock)
    async def test_ensure_jwt_dynamic_generation_failure_with_static_fallback(self, mock_auth_get_jwt):
        with patch('trading_bot.scanner.STATIC_RUGCHECK_API_KEY_OR_JWT', "static_fallback_jwt"), \
             patch('trading_bot.scanner.RUGCHECK_AUTH_SOLANA_PRIVATE_KEY', "test_priv_key_hex_seed"), \
             patch('trading_bot.scanner.RUGCHECK_AUTH_WALLET_PUBLIC_KEY', "test_pub_key_address"):

            mock_auth_get_jwt.return_value = None # Simulate generation failure

            current_scanner = TokenScanner()
            await current_scanner.initialize()

            # If dynamic generation fails, it should retain the static JWT if one was loaded initially.
            self.assertEqual(current_scanner.rugcheck_jwt, "static_fallback_jwt")
            self.assertTrue(current_scanner.rugcheck_jwt_generation_attempted)
            await current_scanner.close()

    @patch('trading_bot.scanner.get_rugcheck_jwt', new_callable=AsyncMock)
    async def test_ensure_jwt_dynamic_generation_failure_no_static(self, mock_auth_get_jwt):
        with patch('trading_bot.scanner.STATIC_RUGCHECK_API_KEY_OR_JWT', None), \
             patch('trading_bot.scanner.RUGCHECK_AUTH_SOLANA_PRIVATE_KEY', "test_priv_key_hex_seed"), \
             patch('trading_bot.scanner.RUGCHECK_AUTH_WALLET_PUBLIC_KEY', "test_pub_key_address"):

            mock_auth_get_jwt.return_value = None # Simulate generation failure

            current_scanner = TokenScanner()
            await current_scanner.initialize()

            self.assertIsNone(current_scanner.rugcheck_jwt) # No static JWT to fall back on
            self.assertTrue(current_scanner.rugcheck_jwt_generation_attempted)
            await current_scanner.close()


    @patch('trading_bot.scanner.get_rugcheck_jwt', new_callable=AsyncMock)
    async def test_ensure_jwt_generation_not_attempted_if_no_dynamic_keys(self, mock_auth_get_jwt):
        with patch('trading_bot.scanner.STATIC_RUGCHECK_API_KEY_OR_JWT', "only_static_jwt"), \
             patch('trading_bot.scanner.RUGCHECK_AUTH_SOLANA_PRIVATE_KEY', None), \
             patch('trading_bot.scanner.RUGCHECK_AUTH_WALLET_PUBLIC_KEY', None):

            current_scanner = TokenScanner()
            await current_scanner.initialize()

            self.assertEqual(current_scanner.rugcheck_jwt, "only_static_jwt")
            mock_auth_get_jwt.assert_not_called()
            # rugcheck_jwt_generation_attempted should be False if dynamic keys are missing
            self.assertFalse(current_scanner.rugcheck_jwt_generation_attempted)
            await current_scanner.close()

    @patch('trading_bot.scanner.get_rugcheck_jwt', new_callable=AsyncMock)
    async def test_ensure_jwt_generation_attempted_flag_prevents_retry(self, mock_auth_get_jwt):
        with patch('trading_bot.scanner.STATIC_RUGCHECK_API_KEY_OR_JWT', None), \
             patch('trading_bot.scanner.RUGCHECK_AUTH_SOLANA_PRIVATE_KEY', "test_priv_key"), \
             patch('trading_bot.scanner.RUGCHECK_AUTH_WALLET_PUBLIC_KEY', "test_pub_key"):

            mock_auth_get_jwt.return_value = None # First attempt fails

            # Create a scanner instance that will be used across multiple calls to _ensure_rugcheck_jwt
            test_scanner_instance = TokenScanner()
            await test_scanner_instance.initialize() # Calls _ensure_rugcheck_jwt, attempt made, jwt is None

            self.assertTrue(test_scanner_instance.rugcheck_jwt_generation_attempted)
            self.assertIsNone(test_scanner_instance.rugcheck_jwt)
            mock_auth_get_jwt.assert_called_once() # Called during initialize

            # Reset mock for the next call check
            mock_auth_get_jwt.reset_mock()

            # Call _ensure_rugcheck_jwt directly again
            await test_scanner_instance._ensure_rugcheck_jwt()
            mock_auth_get_jwt.assert_not_called() # Should not be called again due to the flag
            await test_scanner_instance.close()


    # --- Tests for verify_token_safety_rugcheck ---

    @patch('trading_bot.scanner.RUGCHECK_SCORE_THRESHOLD', 70)
    @patch('trading_bot.scanner.RUGCHECK_CRITICAL_RISK_NAMES', ["Honeypot", "Rugpull"])
    @patch('aiohttp.ClientSession.get', new_callable=AsyncMock)
    async def test_rugcheck_safe_token_with_jwt(self, mock_aiohttp_get, _mock_crit, _mock_score):
        self.scanner.rugcheck_jwt = "test_jwt_for_header" # Set JWT

        mock_aiohttp_get.return_value.__aenter__.return_value.status = 200
        mock_aiohttp_get.return_value.__aenter__.return_value.json = AsyncMock(return_value={
            "scoreNormalised": 80, "rugged": False, "risks": []
        })

        result = await self.scanner.verify_token_safety_rugcheck(self.scanner.session, "test_safe_token")

        self.assertTrue(result['is_safe'])
        mock_aiohttp_get.assert_called_once()
        called_headers = mock_aiohttp_get.call_args[1].get('headers', {})
        self.assertEqual(called_headers.get('Authorization'), "Bearer test_jwt_for_header")

    @patch('trading_bot.scanner.RUGCHECK_SCORE_THRESHOLD', 70)
    @patch('trading_bot.scanner.RUGCHECK_CRITICAL_RISK_NAMES', ["Honeypot", "Rugpull"])
    @patch('aiohttp.ClientSession.get', new_callable=AsyncMock)
    async def test_rugcheck_safe_token_no_jwt(self, mock_aiohttp_get, _mock_crit, _mock_score):
        self.scanner.rugcheck_jwt = None # Ensure no JWT

        mock_aiohttp_get.return_value.__aenter__.return_value.status = 200
        mock_aiohttp_get.return_value.__aenter__.return_value.json = AsyncMock(return_value={
            "scoreNormalised": 80, "rugged": False, "risks": []
        })

        result = await self.scanner.verify_token_safety_rugcheck(self.scanner.session, "test_safe_token_no_jwt")

        self.assertTrue(result['is_safe'])
        mock_aiohttp_get.assert_called_once()
        called_headers = mock_aiohttp_get.call_args[1].get('headers', {})
        self.assertNotIn('Authorization', called_headers)

    @patch('trading_bot.scanner.RUGCHECK_CRITICAL_RISK_NAMES', ["Honeypot", "Rugpull", "MintAuthorityEnabled"])
    @patch('trading_bot.scanner.RUGCHECK_SCORE_THRESHOLD', 70)
    @patch('aiohttp.ClientSession.get', new_callable=AsyncMock)
    async def test_rugcheck_unsafe_mint_authority_enabled(self, mock_get, _mock_score, _mock_crit):
        mock_get.return_value.__aenter__.return_value.status = 200
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(return_value={
            "scoreNormalised": 85, # Good score
            "rugged": False,
            "risks": [{"name": "MintAuthorityEnabled", "level": "critical", "description": "Token minting is still enabled."}]
        })
        result = await self.scanner.verify_token_safety_rugcheck(self.scanner.session, "test_mint_enabled_token")

        self.assertFalse(result['is_safe'])
        self.assertTrue(any("Critical risk: MintAuthorityEnabled" in reason for reason in result['reasons']))


    # Note: Other tests for verify_token_safety_rugcheck (low_score, other critical_risk, api_error, 404)
    # from the previous version of this file are still relevant and should be kept.
    # They are assumed to be here from the previous file content.
    # Adding them back if they were removed by the overwrite:

    @patch('trading_bot.scanner.RUGCHECK_SCORE_THRESHOLD', 50)
    @patch('aiohttp.ClientSession.get', new_callable=AsyncMock)
    async def test_rugcheck_unsafe_low_score_from_previous(self, mock_get, _mock_score_thresh): # Renamed
        mock_get.return_value.__aenter__.return_value.status = 200
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(return_value={
            "scoreNormalised": 30, "rugged": False, "risks": []
        })
        result = await self.scanner.verify_token_safety_rugcheck(self.scanner.session, "test_low_score_token")
        self.assertFalse(result['is_safe'])
        self.assertIn("Score (30) is below threshold (50)", result['reasons'])

    @patch('aiohttp.ClientSession.get', new_callable=AsyncMock)
    async def test_rugcheck_api_error_client_error_from_previous(self, mock_get): # Renamed
        mock_get.side_effect = aiohttp.ClientError("API Test Error")
        result = await self.scanner.verify_token_safety_rugcheck(self.scanner.session, "test_api_error_token")
        self.assertFalse(result['is_safe'])
        self.assertIn("Unexpected error: API Test Error", result['reasons'])
        self.assertIn("Unexpected error: API Test Error", result['api_error'])

    @patch('aiohttp.ClientSession.get', new_callable=AsyncMock)
    async def test_rugcheck_token_not_found_404_from_previous(self, mock_get): # Renamed
        mock_response = mock_get.return_value.__aenter__.return_value
        mock_response.status = 404
        mock_response.text = AsyncMock(return_value="Not Found")
        result = await self.scanner.verify_token_safety_rugcheck(self.scanner.session, "test_404_token")
        self.assertFalse(result['is_safe'])
        self.assertIn("Token not found on RugCheck", result['reasons'])
        self.assertIn("Token not found (404)", result['api_error'])


    # --- Tests for analyze_token_metrics (focus on market cap) ---
    # These tests should use patching for config values at the 'trading_bot.scanner' module level.
    @patch('trading_bot.scanner.TARGET_MARKET_CAP_TO_SCAN', 30000)
    def test_analyze_mcap_below_target(self, _mock_config_target_mcap):
        mock_token_data = {"baseToken": {"symbol": "T"}, "pairAddress": "P", "fdv": 20000}
        passed, reason = self.scanner.analyze_token_metrics(mock_token_data)
        self.assertFalse(passed)
        self.assertIn("MC $20,000 < Target $30,000", reason)

    @patch('trading_bot.scanner.TARGET_MARKET_CAP_TO_SCAN', 30000)
    @patch('trading_bot.scanner.MAX_MARKET_CAP', 750000)
    def test_analyze_mcap_above_max(self, _mock_config_max_mcap, _mock_config_target_mcap):
        mock_token_data = {"baseToken": {"symbol": "T"}, "pairAddress": "P", "fdv": 800000}
        passed, reason = self.scanner.analyze_token_metrics(mock_token_data)
        self.assertFalse(passed)
        self.assertIn("MC $800,000 > Max $750,000", reason)

    @patch('trading_bot.scanner.TARGET_MARKET_CAP_TO_SCAN', 30000)
    @patch('trading_bot.scanner.MAX_MARKET_CAP', 750000)
    @patch('trading_bot.scanner.MAX_TOKEN_AGE_HOURS', 6)
    @patch('trading_bot.scanner.MIN_LIQUIDITY', 1000)
    def test_analyze_mcap_in_range_fails_on_next_check(self, _m1, _m2, _m3, _m4): # Mocks for brevity
        mock_token_data = {
            "baseToken": {"symbol": "TEST"}, "pairAddress": "PAIR_XYZ", "fdv": 50000,
            "pairCreatedAt": (datetime.now() - timedelta(hours=10)).timestamp() * 1000, # Too old
            "liquidity": {"usd": "50000"}, "txns": {"h1": {"buys": 50, "sells": 50}},
            "volume": {"h1": "1000", "h24": "10000"}, "priceChange": {"h1": "1"}
        }
        passed, reason = self.scanner.analyze_token_metrics(mock_token_data)
        self.assertFalse(passed)
        self.assertIn("Token too old", reason)

    # --- Tests for scan_new_tokens (integration - simplified) ---
    @patch('trading_bot.scanner.TokenScanner.analyze_token_metrics')
    @patch('trading_bot.scanner.TokenScanner.verify_token_safety_rugcheck', new_callable=AsyncMock)
    @patch('trading_bot.scanner.TokenScanner.get_social_sentiment_placeholder', new_callable=AsyncMock)
    @patch('aiohttp.ClientSession.get', new_callable=AsyncMock) # Mocks the DexScreener call in scan_new_tokens
    async def test_scan_new_tokens_filters_unsafe_rugcheck(self, mock_dex_get, mock_sentiment, mock_rugcheck, mock_analyze_metrics):
        mock_dex_get.return_value.__aenter__.return_value.status = 200
        mock_dex_get.return_value.__aenter__.return_value.json = AsyncMock(return_value={
            "pairs": [{"baseToken": {"address": "addr1", "symbol": "UNSAFE"}, "pairAddress": "pair1", "dexId": "dex1"}]})
        mock_analyze_metrics.return_value = (True, "Passed primary analysis")
        mock_rugcheck.return_value = {"is_safe": False, "reasons": ["Test Unsafe by RugCheck"], "api_error": None}

        await self.scanner.scan_new_tokens()
        self.assertEqual(len(self.scanner.potential_tokens), 0)
        mock_rugcheck.assert_called_once_with(self.scanner.session, "addr1")

    @patch('trading_bot.scanner.TokenScanner.analyze_token_metrics')
    @patch('trading_bot.scanner.TokenScanner.verify_token_safety_rugcheck', new_callable=AsyncMock)
    @patch('trading_bot.scanner.TokenScanner.get_social_sentiment_placeholder', new_callable=AsyncMock)
    @patch('aiohttp.ClientSession.get', new_callable=AsyncMock)
    async def test_scan_new_tokens_filters_failed_metrics(self, mock_dex_get, mock_sentiment, mock_rugcheck, mock_analyze_metrics):
        mock_dex_get.return_value.__aenter__.return_value.status = 200
        mock_dex_get.return_value.__aenter__.return_value.json = AsyncMock(return_value={
             "pairs": [{"baseToken": {"address": "addr2", "symbol": "FAILMETRIC"}, "pairAddress": "pair2", "dexId": "dex2"}]})
        mock_analyze_metrics.return_value = (False, "Failed metrics analysis")

        await self.scanner.scan_new_tokens()
        self.assertEqual(len(self.scanner.potential_tokens), 0)
        mock_analyze_metrics.assert_called_once()
        mock_rugcheck.assert_not_called()

    @patch('trading_bot.scanner.TARGET_MARKET_CAP_TO_SCAN', 30000)
    @patch('trading_bot.scanner.MAX_MARKET_CAP', 750000)
    @patch('trading_bot.scanner.MAX_TOKEN_AGE_HOURS', 24)
    @patch('trading_bot.scanner.MIN_LIQUIDITY', 50000)
    @patch('trading_bot.scanner.MIN_TRANSACTIONS', 50)
    @patch('trading_bot.scanner.MIN_BUY_SELL_RATIO', 0.1)
    @patch('trading_bot.scanner.VOLUME_SPIKE_THRESHOLD', 0.1)
    @patch('trading_bot.scanner.MIN_HOLDER_COUNT', 100)
    @patch('trading_bot.scanner.TokenScanner.verify_token_safety_rugcheck', new_callable=AsyncMock)
    @patch('trading_bot.scanner.TokenScanner.get_social_sentiment_placeholder', new_callable=AsyncMock)
    @patch('aiohttp.ClientSession.get', new_callable=AsyncMock) # For DexScreener call in scan_new_tokens
    async def test_scan_new_tokens_adds_valid_token(self, mock_dex_get, mock_sentiment, mock_rugcheck,
                                                 _mhc, _vst, _mbsr, _mt, _ml, _mtah, _mmc, _tmtcs): # Patched config mocks
        test_token_addr, test_token_sym, test_pair_addr = "addr_safe", "SAFE", "pair_safe"
        mock_dex_pair_data = {
            "baseToken": {"address": test_token_addr, "symbol": test_token_sym},
            "pairAddress": test_pair_addr, "dexId": "dex_s", "priceUsd": "1", "fdv": "50000",
            "liquidity": {"usd": "60000"}, "volume": {"h24": "10000"},
            "pairCreatedAt": (datetime.now() - timedelta(hours=1)).timestamp() * 1000,
            "txns": {"h1": {"buys": 100, "sells": 10}}, "priceChange": {"h1": "5"},
            "holders": {"total": 200}
        }
        mock_dex_get.return_value.__aenter__.return_value.status = 200
        mock_dex_get.return_value.__aenter__.return_value.json = AsyncMock(return_value={"pairs": [mock_dex_pair_data]})

        # analyze_token_metrics will use the patched config values
        # No need to mock analyze_token_metrics itself if we want to test its integration with patched configs

        mock_rugcheck_assessment = {"is_safe": True, "score_normalised": 90, "reasons": [], "api_error": None}
        mock_rugcheck.return_value = mock_rugcheck_assessment
        mock_sentiment.return_value = {"sentiment_score": 0.7, "sentiment": "positive"}

        await self.scanner.scan_new_tokens()

        self.assertEqual(len(self.scanner.potential_tokens), 1)
        added_token = self.scanner.potential_tokens[0]
        self.assertEqual(added_token['address'], test_token_addr)
        self.assertEqual(added_token['rugcheck_assessment'], mock_rugcheck_assessment)
        self.assertIn('social_sentiment', added_token)

if __name__ == '__main__':
    unittest.main()

```
