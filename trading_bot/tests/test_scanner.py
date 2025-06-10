import asyncio
import unittest
from unittest.mock import AsyncMock, patch
import logging
from datetime import datetime, timedelta
import json

import aiohttp

from trading_bot.scanner import TokenScanner
from trading_bot.auth_utils import get_rugcheck_jwt
# Import config names that will be patched at the module level of scanner
from trading_bot.config import (
    STATIC_RUGCHECK_JWT,
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
    MIN_HOLDER_COUNT,
    FILTER_FOR_PUMPFUN_ONLY, # For patching
    PUMPFUN_ADDRESS_SUFFIX # For patching
)

logging.disable(logging.CRITICAL)

class TestTokenScanner(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.scanner = TokenScanner()
        self.scanner.rugcheck_jwt = None
        self.scanner.rugcheck_jwt_generation_attempted = False
        self.scanner.potential_tokens = [] # Explicitly reset here for clarity for scan_new_tokens tests

    async def asyncSetUp(self):
        if not self.scanner.session or self.scanner.session.closed:
            await self.scanner.initialize()

    async def asyncTearDown(self):
        if self.scanner.session:
            await self.scanner.close()

    # --- Tests for _ensure_rugcheck_jwt ---
    # [Existing tests for _ensure_rugcheck_jwt remain here - unchanged from previous step]
    @patch('trading_bot.scanner.get_rugcheck_jwt', new_callable=AsyncMock)
    async def test_ensure_jwt_uses_static_if_present_and_no_dynamic_keys(self, mock_auth_get_jwt):
        with patch('trading_bot.scanner.STATIC_RUGCHECK_JWT', "static_jwt_token_from_config"), \
             patch('trading_bot.scanner.RUGCHECK_AUTH_SOLANA_PRIVATE_KEY', None), \
             patch('trading_bot.scanner.RUGCHECK_AUTH_WALLET_PUBLIC_KEY', None):
            current_scanner = TokenScanner()
            await current_scanner.initialize()
            self.assertEqual(current_scanner.rugcheck_jwt, "static_jwt_token_from_config")
            mock_auth_get_jwt.assert_not_called()
            await current_scanner.close()

    @patch('trading_bot.scanner.get_rugcheck_jwt', new_callable=AsyncMock)
    async def test_ensure_jwt_generates_dynamically_overwrites_static(self, mock_auth_get_jwt):
        with patch('trading_bot.scanner.STATIC_RUGCHECK_JWT', "old_static_jwt_in_config"), \
             patch('trading_bot.scanner.RUGCHECK_AUTH_SOLANA_PRIVATE_KEY', "test_priv_key_hex_seed"), \
             patch('trading_bot.scanner.RUGCHECK_AUTH_WALLET_PUBLIC_KEY', "test_pub_key_address"):
            mock_auth_get_jwt.return_value = "generated_dynamic_jwt"
            current_scanner = TokenScanner()
            await current_scanner.initialize()
            self.assertEqual(current_scanner.rugcheck_jwt, "generated_dynamic_jwt")
            mock_auth_get_jwt.assert_called_once_with(
                current_scanner.session, "test_priv_key_hex_seed", "test_pub_key_address")
            await current_scanner.close()

    @patch('trading_bot.scanner.get_rugcheck_jwt', new_callable=AsyncMock)
    async def test_ensure_jwt_dynamic_generation_failure_with_static_fallback(self, mock_auth_get_jwt):
        with patch('trading_bot.scanner.STATIC_RUGCHECK_JWT', "static_fallback_jwt_in_config"), \
             patch('trading_bot.scanner.RUGCHECK_AUTH_SOLANA_PRIVATE_KEY', "test_priv_key_hex_seed"), \
             patch('trading_bot.scanner.RUGCHECK_AUTH_WALLET_PUBLIC_KEY', "test_pub_key_address"):
            mock_auth_get_jwt.return_value = None
            current_scanner = TokenScanner()
            await current_scanner.initialize()
            self.assertEqual(current_scanner.rugcheck_jwt, "static_fallback_jwt_in_config")
            self.assertTrue(current_scanner.rugcheck_jwt_generation_attempted)
            await current_scanner.close()

    @patch('trading_bot.scanner.get_rugcheck_jwt', new_callable=AsyncMock)
    async def test_ensure_jwt_dynamic_generation_failure_no_static(self, mock_auth_get_jwt):
        with patch('trading_bot.scanner.STATIC_RUGCHECK_JWT', None), \
             patch('trading_bot.scanner.RUGCHECK_AUTH_SOLANA_PRIVATE_KEY', "test_priv_key_hex_seed"), \
             patch('trading_bot.scanner.RUGCHECK_AUTH_WALLET_PUBLIC_KEY', "test_pub_key_address"):
            mock_auth_get_jwt.return_value = None
            current_scanner = TokenScanner()
            await current_scanner.initialize()
            self.assertIsNone(current_scanner.rugcheck_jwt)
            self.assertTrue(current_scanner.rugcheck_jwt_generation_attempted)
            await current_scanner.close()

    @patch('trading_bot.scanner.get_rugcheck_jwt', new_callable=AsyncMock)
    async def test_ensure_jwt_generation_not_attempted_if_no_dynamic_keys(self, mock_auth_get_jwt):
        with patch('trading_bot.scanner.STATIC_RUGCHECK_JWT', "only_static_jwt_in_config"), \
             patch('trading_bot.scanner.RUGCHECK_AUTH_SOLANA_PRIVATE_KEY', None), \
             patch('trading_bot.scanner.RUGCHECK_AUTH_WALLET_PUBLIC_KEY', None):
            current_scanner = TokenScanner()
            await current_scanner.initialize()
            self.assertEqual(current_scanner.rugcheck_jwt, "only_static_jwt_in_config")
            mock_auth_get_jwt.assert_not_called()
            self.assertFalse(current_scanner.rugcheck_jwt_generation_attempted)
            await current_scanner.close()

    @patch('trading_bot.scanner.get_rugcheck_jwt', new_callable=AsyncMock)
    async def test_ensure_jwt_generation_attempted_flag_prevents_retry(self, mock_auth_get_jwt):
        with patch('trading_bot.scanner.STATIC_RUGCHECK_JWT', None), \
             patch('trading_bot.scanner.RUGCHECK_AUTH_SOLANA_PRIVATE_KEY', "test_priv_key"), \
             patch('trading_bot.scanner.RUGCHECK_AUTH_WALLET_PUBLIC_KEY', "test_pub_key"):
            mock_auth_get_jwt.return_value = None
            test_scanner_instance = TokenScanner()
            await test_scanner_instance.initialize()
            self.assertTrue(test_scanner_instance.rugcheck_jwt_generation_attempted)
            self.assertIsNone(test_scanner_instance.rugcheck_jwt)
            mock_auth_get_jwt.assert_called_once()
            mock_auth_get_jwt.reset_mock()
            await test_scanner_instance._ensure_rugcheck_jwt()
            mock_auth_get_jwt.assert_not_called()
            await test_scanner_instance.close()

    # --- Tests for verify_token_safety_rugcheck ---
    # [Existing tests for verify_token_safety_rugcheck remain here - unchanged from previous step]
    @patch('trading_bot.scanner.RUGCHECK_SCORE_THRESHOLD', 70)
    @patch('trading_bot.scanner.RUGCHECK_CRITICAL_RISK_NAMES', ["Honeypot", "Rugpull"])
    @patch('aiohttp.ClientSession.get', new_callable=AsyncMock)
    async def test_rugcheck_safe_token_with_jwt(self, mock_aiohttp_get, _mock_crit, _mock_score):
        self.scanner.rugcheck_jwt = "test_jwt_for_header"
        mock_aiohttp_get.return_value.__aenter__.return_value.status = 200
        mock_aiohttp_get.return_value.__aenter__.return_value.json = AsyncMock(return_value={
            "scoreNormalised": 80, "rugged": False, "risks": []})
        result = await self.scanner.verify_token_safety_rugcheck(self.scanner.session, "test_safe_token")
        self.assertTrue(result['is_safe'])
        mock_aiohttp_get.assert_called_once()
        called_headers = mock_aiohttp_get.call_args[1].get('headers', {})
        self.assertEqual(called_headers.get('Authorization'), "Bearer test_jwt_for_header")

    @patch('trading_bot.scanner.RUGCHECK_SCORE_THRESHOLD', 70)
    @patch('trading_bot.scanner.RUGCHECK_CRITICAL_RISK_NAMES', ["Honeypot", "Rugpull"])
    @patch('aiohttp.ClientSession.get', new_callable=AsyncMock)
    async def test_rugcheck_safe_token_no_jwt(self, mock_aiohttp_get, _mock_crit, _mock_score):
        self.scanner.rugcheck_jwt = None
        mock_aiohttp_get.return_value.__aenter__.return_value.status = 200
        mock_aiohttp_get.return_value.__aenter__.return_value.json = AsyncMock(return_value={
            "scoreNormalised": 80, "rugged": False, "risks": []})
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
            "scoreNormalised": 85, "rugged": False,
            "risks": [{"name": "MintAuthorityEnabled", "level": "critical", "description": "Token minting is still enabled."}]})
        result = await self.scanner.verify_token_safety_rugcheck(self.scanner.session, "test_mint_enabled_token")
        self.assertFalse(result['is_safe'])
        self.assertTrue(any("Critical risk: MintAuthorityEnabled" in reason for reason in result['reasons']))

    @patch('trading_bot.scanner.RUGCHECK_SCORE_THRESHOLD', 50)
    @patch('aiohttp.ClientSession.get', new_callable=AsyncMock)
    async def test_rugcheck_unsafe_low_score(self, mock_get, _mock_score_thresh):
        mock_get.return_value.__aenter__.return_value.status = 200
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(return_value={
            "scoreNormalised": 30, "rugged": False, "risks": []})
        result = await self.scanner.verify_token_safety_rugcheck(self.scanner.session, "test_low_score_token")
        self.assertFalse(result['is_safe'])
        self.assertIn("Score (30) is below threshold (50)", result['reasons'])

    @patch('aiohttp.ClientSession.get', new_callable=AsyncMock)
    async def test_rugcheck_api_error_client_error(self, mock_get):
        mock_get.side_effect = aiohttp.ClientError("API Test Error")
        result = await self.scanner.verify_token_safety_rugcheck(self.scanner.session, "test_api_error_token")
        self.assertFalse(result['is_safe'])
        self.assertIn("Unexpected error: API Test Error", result['reasons'])
        self.assertIn("Unexpected error: API Test Error", result['api_error'])

    @patch('aiohttp.ClientSession.get', new_callable=AsyncMock)
    async def test_rugcheck_token_not_found_404(self, mock_get):
        mock_response = mock_get.return_value.__aenter__.return_value
        mock_response.status = 404
        mock_response.text = AsyncMock(return_value="Not Found")
        result = await self.scanner.verify_token_safety_rugcheck(self.scanner.session, "test_404_token")
        self.assertFalse(result['is_safe'])
        self.assertIn("Token not found on RugCheck", result['reasons'])
        self.assertIn("Token not found (404)", result['api_error'])

    @patch('aiohttp.ClientSession.get', new_callable=AsyncMock)
    @patch('trading_bot.scanner.RUGCHECK_SCORE_THRESHOLD', 70)
    async def test_rugcheck_malformed_risks_data(self, mock_aiohttp_get, _mock_score_thresh):
        mock_response = mock_aiohttp_get.return_value.__aenter__.return_value
        mock_response.status = 200
        malformed_risks = {"error": "should be a list"}
        mock_response.json = AsyncMock(return_value={
            "scoreNormalised": 80, "rugged": False, "risks": malformed_risks })
        mock_response.text = AsyncMock(return_value=json.dumps({
            "scoreNormalised": 80, "rugged": False, "risks": malformed_risks}))
        result = await self.scanner.verify_token_safety_rugcheck(self.scanner.session, "test_token_malformed_risks")
        self.assertFalse(result['is_safe'])
        self.assertIn("Malformed 'risks' field in RugCheck API response (expected a list).", result['reasons'])
        self.assertIsNone(result['api_error'])
        self.assertEqual(result['risks'], malformed_risks)

    @patch('aiohttp.ClientSession.get', new_callable=AsyncMock)
    @patch('trading_bot.scanner.RUGCHECK_SCORE_THRESHOLD', 70)
    async def test_rugcheck_missing_risks_data(self, mock_aiohttp_get, _mock_score_thresh):
        mock_response = mock_aiohttp_get.return_value.__aenter__.return_value
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"scoreNormalised": 80, "rugged": False})
        mock_response.text = AsyncMock(return_value=json.dumps({"scoreNormalised": 80, "rugged": False}))
        result = await self.scanner.verify_token_safety_rugcheck(self.scanner.session, "test_token_missing_risks")
        self.assertTrue(result['is_safe'])
        self.assertEqual(result['reasons'], [])
        self.assertIsNone(result['risks'])

    # --- Tests for analyze_token_metrics ---
    # [Existing tests for analyze_token_metrics remain here - unchanged from previous step]
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
    def test_analyze_mcap_in_range_fails_on_next_check(self, _m1, _m2, _m3, _m4):
        mock_token_data = {
            "baseToken": {"symbol": "TEST"}, "pairAddress": "PAIR_XYZ", "fdv": 50000,
            "pairCreatedAt": (datetime.now() - timedelta(hours=10)).timestamp() * 1000,
            "liquidity": {"usd": "50000"}, "txns": {"h1": {"buys": 50, "sells": 50}},
            "volume": {"h1": "1000", "h24": "10000"}, "priceChange": {"h1": "1"}}
        passed, reason = self.scanner.analyze_token_metrics(mock_token_data)
        self.assertFalse(passed)
        self.assertIn("Token too old", reason)

    # --- Tests for scan_new_tokens (Pump.fun filter logic) ---
    @patch('trading_bot.scanner.FILTER_FOR_PUMPFUN_ONLY', True)
    @patch('trading_bot.scanner.PUMPFUN_ADDRESS_SUFFIX', "pump")
    @patch('aiohttp.ClientSession.get', new_callable=AsyncMock)
    @patch('trading_bot.scanner.TokenScanner.analyze_token_metrics', new_callable=AsyncMock)
    @patch('trading_bot.scanner.TokenScanner.verify_token_safety_rugcheck', new_callable=AsyncMock)
    @patch('trading_bot.scanner.TokenScanner.get_social_sentiment_placeholder', new_callable=AsyncMock)
    async def test_scan_new_tokens_pumpfun_filter_active_match(self, mock_sentiment, mock_rugcheck, mock_analyze, mock_session_get):
        mock_api_response = mock_session_get.return_value.__aenter__.return_value
        mock_api_response.status = 200
        mock_api_response.json = AsyncMock(return_value={
            "pairs": [{"baseToken": {"address": "testtoken1pump", "symbol": "PUMP1"},
                        "pairAddress": "pair1", "priceUsd": "10",
                        "liquidity": {"usd": "50000"}, "volume": {"h24": "100000"},
                        "fdv": "60000", "pairCreatedAt": datetime.now().timestamp() * 1000,
                        "txns": {"h1": {"buys":10, "sells":5}},
                        "priceChange": {"h1": 5}
                       }]
        })
        mock_analyze.return_value = (True, "Passed analysis")
        mock_rugcheck.return_value = {'is_safe': True, 'reasons': [], 'score_normalised': 80, 'api_error': None, 'risks': []}
        mock_sentiment.return_value = {'sentiment_score': 0.5, 'sentiment': 'neutral'}

        await self.scanner.scan_new_tokens()
        self.assertEqual(len(self.scanner.potential_tokens), 1)
        self.assertEqual(self.scanner.potential_tokens[0]['address'], "testtoken1pump")
        mock_analyze.assert_called_once()

    @patch('trading_bot.scanner.FILTER_FOR_PUMPFUN_ONLY', True)
    @patch('trading_bot.scanner.PUMPFUN_ADDRESS_SUFFIX', "pump")
    @patch('aiohttp.ClientSession.get', new_callable=AsyncMock)
    @patch('trading_bot.scanner.TokenScanner.analyze_token_metrics', new_callable=AsyncMock)
    # No need to patch rugcheck & sentiment as analyze_token_metrics won't be called
    async def test_scan_new_tokens_pumpfun_filter_active_no_match(self, mock_analyze_metrics, mock_session_get):
        mock_api_response = mock_session_get.return_value.__aenter__.return_value
        mock_api_response.status = 200
        mock_api_response.json = AsyncMock(return_value={
            "pairs": [{"baseToken": {"address": "testtoken2xyz", "symbol": "XYZ1"}, "pairAddress": "pair2"}]
        })

        await self.scanner.scan_new_tokens()
        self.assertEqual(len(self.scanner.potential_tokens), 0)
        mock_analyze_metrics.assert_not_called()

    @patch('trading_bot.scanner.FILTER_FOR_PUMPFUN_ONLY', False) # Filter INACTIVE
    @patch('trading_bot.scanner.PUMPFUN_ADDRESS_SUFFIX', "pump")
    @patch('aiohttp.ClientSession.get', new_callable=AsyncMock)
    @patch('trading_bot.scanner.TokenScanner.analyze_token_metrics', new_callable=AsyncMock)
    @patch('trading_bot.scanner.TokenScanner.verify_token_safety_rugcheck', new_callable=AsyncMock)
    @patch('trading_bot.scanner.TokenScanner.get_social_sentiment_placeholder', new_callable=AsyncMock)
    async def test_scan_new_tokens_pumpfun_filter_inactive(self, mock_sentiment, mock_rugcheck, mock_analyze, mock_session_get):
        mock_api_response = mock_session_get.return_value.__aenter__.return_value
        mock_api_response.status = 200
        mock_api_response.json = AsyncMock(return_value={
            "pairs": [{"baseToken": {"address": "testtoken3other", "symbol": "OTH3"},
                        "pairAddress": "pair3", "priceUsd": "20",
                        "liquidity": {"usd": "60000"}, "volume": {"h24": "120000"},
                        "fdv": "70000", "pairCreatedAt": datetime.now().timestamp() * 1000,
                        "txns": {"h1": {"buys":10, "sells":5}},
                        "priceChange": {"h1": 5}
                       }]
        })
        mock_analyze.return_value = (True, "Passed analysis")
        mock_rugcheck.return_value = {'is_safe': True, 'reasons': [], 'score_normalised': 80, 'api_error': None, 'risks': []}
        mock_sentiment.return_value = {'sentiment_score': 0.5, 'sentiment': 'neutral'}

        await self.scanner.scan_new_tokens()
        self.assertEqual(len(self.scanner.potential_tokens), 1)
        self.assertEqual(self.scanner.potential_tokens[0]['address'], "testtoken3other")

    @patch('trading_bot.scanner.FILTER_FOR_PUMPFUN_ONLY', True)
    @patch('trading_bot.scanner.PUMPFUN_ADDRESS_SUFFIX', "") # EMPTY suffix
    @patch('aiohttp.ClientSession.get', new_callable=AsyncMock)
    @patch('trading_bot.scanner.TokenScanner.analyze_token_metrics', new_callable=AsyncMock)
    @patch('trading_bot.scanner.TokenScanner.verify_token_safety_rugcheck', new_callable=AsyncMock)
    @patch('trading_bot.scanner.TokenScanner.get_social_sentiment_placeholder', new_callable=AsyncMock)
    async def test_scan_new_tokens_pumpfun_filter_active_empty_suffix(self, mock_sentiment, mock_rugcheck, mock_analyze, mock_session_get):
        mock_api_response = mock_session_get.return_value.__aenter__.return_value
        mock_api_response.status = 200
        mock_api_response.json = AsyncMock(return_value={
            "pairs": [{"baseToken": {"address": "testtoken4any", "symbol": "ANY4"},
                        "pairAddress": "pair4", "priceUsd": "30",
                        "liquidity": {"usd": "70000"}, "volume": {"h24": "130000"},
                        "fdv": "80000", "pairCreatedAt": datetime.now().timestamp() * 1000,
                        "txns": {"h1": {"buys":10, "sells":5}},
                        "priceChange": {"h1": 5}
                        }]
        })
        mock_analyze.return_value = (True, "Passed analysis")
        mock_rugcheck.return_value = {'is_safe': True, 'reasons': [], 'score_normalised': 80, 'api_error': None, 'risks': []}
        mock_sentiment.return_value = {'sentiment_score': 0.5, 'sentiment': 'neutral'}

        await self.scanner.scan_new_tokens()
        self.assertEqual(len(self.scanner.potential_tokens), 1)
        self.assertEqual(self.scanner.potential_tokens[0]['address'], "testtoken4any")

    # --- Existing Tests for scan_new_tokens (general filtering) ---
    # [These tests were here before, ensure they are still valid and correctly ordered/patched]
    @patch('trading_bot.scanner.TokenScanner.analyze_token_metrics')
    @patch('trading_bot.scanner.TokenScanner.verify_token_safety_rugcheck', new_callable=AsyncMock)
    @patch('trading_bot.scanner.TokenScanner.get_social_sentiment_placeholder', new_callable=AsyncMock)
    @patch('aiohttp.ClientSession.get', new_callable=AsyncMock)
    async def test_scan_new_tokens_filters_unsafe_rugcheck_original(self, mock_dex_get, mock_sentiment, mock_rugcheck, mock_analyze_metrics):
        mock_dex_get.return_value.__aenter__.return_value.status = 200
        mock_dex_get.return_value.__aenter__.return_value.json = AsyncMock(return_value={
            "pairs": [{"baseToken": {"address": "addr1", "symbol": "UNSAFE"}, "pairAddress": "pair1", "dexId": "dex1"}]})
        mock_analyze_metrics.return_value = (True, "Passed primary analysis")
        mock_rugcheck.return_value = {"is_safe": False, "reasons": ["Test Unsafe by RugCheck"], "api_error": None}

        # Ensure Pumpfun filter is off for this generic test
        with patch('trading_bot.scanner.FILTER_FOR_PUMPFUN_ONLY', False):
            await self.scanner.scan_new_tokens()
        self.assertEqual(len(self.scanner.potential_tokens), 0)
        mock_rugcheck.assert_called_once_with(self.scanner.session, "addr1")

    @patch('trading_bot.scanner.TokenScanner.analyze_token_metrics')
    @patch('trading_bot.scanner.TokenScanner.verify_token_safety_rugcheck', new_callable=AsyncMock)
    @patch('trading_bot.scanner.TokenScanner.get_social_sentiment_placeholder', new_callable=AsyncMock)
    @patch('aiohttp.ClientSession.get', new_callable=AsyncMock)
    async def test_scan_new_tokens_filters_failed_metrics_original(self, mock_dex_get, mock_sentiment, mock_rugcheck, mock_analyze_metrics):
        mock_dex_get.return_value.__aenter__.return_value.status = 200
        mock_dex_get.return_value.__aenter__.return_value.json = AsyncMock(return_value={
             "pairs": [{"baseToken": {"address": "addr2", "symbol": "FAILMETRIC"}, "pairAddress": "pair2", "dexId": "dex2"}]})
        mock_analyze_metrics.return_value = (False, "Failed metrics analysis")

        with patch('trading_bot.scanner.FILTER_FOR_PUMPFUN_ONLY', False):
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
    @patch('aiohttp.ClientSession.get', new_callable=AsyncMock)
    async def test_scan_new_tokens_adds_valid_token_original(self, mock_dex_get, mock_sentiment, mock_rugcheck,
                                                 _mhc, _vst, _mbsr, _mt, _ml, _mtah, _mmc, _tmtcs):
        test_token_addr, test_token_sym, test_pair_addr = "addr_safe", "SAFE", "pair_safe"
        mock_dex_pair_data = {
            "baseToken": {"address": test_token_addr, "symbol": test_token_sym},
            "pairAddress": test_pair_addr, "dexId": "dex_s", "priceUsd": "1", "fdv": "50000",
            "liquidity": {"usd": "60000"}, "volume": {"h24": "10000"},
            "pairCreatedAt": (datetime.now() - timedelta(hours=1)).timestamp() * 1000,
            "txns": {"h1": {"buys": 100, "sells": 10}}, "priceChange": {"h1": "5"},
            "holders": {"total": 200}}
        mock_dex_get.return_value.__aenter__.return_value.status = 200
        mock_dex_get.return_value.__aenter__.return_value.json = AsyncMock(return_value={"pairs": [mock_dex_pair_data]})
        mock_rugcheck_assessment = {"is_safe": True, "score_normalised": 90, "reasons": [], "api_error": None}
        mock_rugcheck.return_value = mock_rugcheck_assessment
        mock_sentiment.return_value = {"sentiment_score": 0.7, "sentiment": "positive"}

        with patch('trading_bot.scanner.FILTER_FOR_PUMPFUN_ONLY', False): # Ensure pumpfun filter off for this generic test
            await self.scanner.scan_new_tokens()

        self.assertEqual(len(self.scanner.potential_tokens), 1)
        added_token = self.scanner.potential_tokens[0]
        self.assertEqual(added_token['address'], test_token_addr)
        self.assertEqual(added_token['rugcheck_assessment'], mock_rugcheck_assessment)
        self.assertIn('social_sentiment', added_token)


if __name__ == '__main__':
    unittest.main()

```
