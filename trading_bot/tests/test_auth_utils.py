import asyncio
import unittest
from unittest.mock import patch, AsyncMock
import aiohttp # Import aiohttp for ClientSession type hint if needed by get_rugcheck_jwt
import logging

from trading_bot.auth_utils import get_rugcheck_jwt
# Assuming nacl is available as it's in requirements.txt

# Suppress logging for cleaner test output during tests
logging.disable(logging.CRITICAL)


class TestGetRugcheckJWT(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Create a real ClientSession for tests that might reach the network if not properly mocked,
        # but ensure all network calls are mocked.
        # For get_rugcheck_jwt, the session is passed in, so we'll mock it at the call site.
        self.mock_session = AsyncMock(spec=aiohttp.ClientSession)

        # Using a fixed, valid Ed25519 private key (seed) in hex format (32 bytes = 64 hex characters)
        # This is a known private key for testing purposes ONLY.
        # Corresponds to public key (base58): GqWJ5jK3gY4z1hP9wR8kX7sV2cFbN6mH3aPQuL9tYxVk (example)
        self.test_private_key_hex = "b2d4af06a5a0209b4ab3f336362ce7581f9f0000aaaa1234567890abcdef"
        self.test_public_key = "GqWJ5jK3gY4z1hP9wR8kX7sV2cFbN6mH3aPQuL9tYxVk" # Example public key matching the private key

    async def asyncTearDown(self):
        # If self.mock_session was a real session that was started, close it here.
        # Since it's an AsyncMock, direct close might not be needed unless it has state to reset.
        pass

    async def test_successful_jwt_retrieval(self):
        mock_response = self.mock_session.post.return_value.__aenter__.return_value
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"token": "mock_jwt_token_123"})
        # mock_response.text = AsyncMock(return_value='{"token": "mock_jwt_token_123"}') # .text() not directly used if .json() succeeds

        jwt = await get_rugcheck_jwt(self.mock_session, self.test_private_key_hex, self.test_public_key)
        self.assertEqual(jwt, "mock_jwt_token_123")
        self.mock_session.post.assert_called_once()
        # Optionally, assert call arguments for URL and data structure if needed

    async def test_api_failure_returns_none(self):
        mock_response = self.mock_session.post.return_value.__aenter__.return_value
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal Server Error")
        # Make raise_for_status do something if it's part of the flow being tested for this status
        mock_response.raise_for_status.side_effect = aiohttp.ClientResponseError(
            request_info=AsyncMock(), history=(), status=500, message="Internal Server Error"
        )

        jwt = await get_rugcheck_jwt(self.mock_session, self.test_private_key_hex, self.test_public_key)
        self.assertIsNone(jwt)

    async def test_api_returns_200_but_no_token(self):
        mock_response = self.mock_session.post.return_value.__aenter__.return_value
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"error": "some_error_no_token"})
        # mock_response.text = AsyncMock(return_value='{"error": "some_error_no_token"}')

        jwt = await get_rugcheck_jwt(self.mock_session, self.test_private_key_hex, self.test_public_key)
        self.assertIsNone(jwt)

    async def test_invalid_private_key_hex_format_short(self):
        # HexEncoder.decode will raise ValueError for bad hex string (e.g. non-hex chars or odd length)
        # The code catches generic Exception for SigningKey init, which includes this.
        jwt = await get_rugcheck_jwt(self.mock_session, "shortkey_is_not_hex", self.test_public_key)
        self.assertIsNone(jwt)
        self.mock_session.post.assert_not_called()

    async def test_invalid_private_key_length_not_32_bytes(self):
        # Valid hex, but not 64 hex chars (32 bytes for seed)
        jwt = await get_rugcheck_jwt(self.mock_session, "00112233445566778899aabbccddeeff", self.test_public_key) # 16 bytes hex
        self.assertIsNone(jwt)
        self.mock_session.post.assert_not_called()

    async def test_missing_private_key(self):
        jwt = await get_rugcheck_jwt(self.mock_session, None, self.test_public_key)
        self.assertIsNone(jwt)
        self.mock_session.post.assert_not_called()

    async def test_missing_public_key(self):
        jwt = await get_rugcheck_jwt(self.mock_session, self.test_private_key_hex, None)
        self.assertIsNone(jwt)
        self.mock_session.post.assert_not_called()

    async def test_non_200_error_codes_handled(self):
        error_codes = [400, 401, 403, 404, 503]
        for code in error_codes:
            self.mock_session.reset_mock() # Reset mock for each iteration
            mock_response = self.mock_session.post.return_value.__aenter__.return_value
            mock_response.status = code
            mock_response.text = AsyncMock(return_value=f"Error {code}")
            if code >= 400 : # raise_for_status would typically be called for these
                 mock_response.raise_for_status.side_effect = aiohttp.ClientResponseError(
                    request_info=AsyncMock(), history=(), status=code, message=f"Error {code}"
                )

            jwt = await get_rugcheck_jwt(self.mock_session, self.test_private_key_hex, self.test_public_key)
            self.assertIsNone(jwt, f"JWT should be None for status code {code}")

if __name__ == '__main__':
    unittest.main()
```
