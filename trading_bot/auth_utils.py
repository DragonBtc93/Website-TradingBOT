import asyncio
import time
import json
import aiohttp
import logging
from typing import Optional
from nacl.signing import SigningKey
from nacl.encoding import HexEncoder

logger = logging.getLogger(__name__)

async def get_rugcheck_jwt(
    session: aiohttp.ClientSession,
    private_key_hex: str,
    public_key: str, # This is the wallet address string
    auth_url: str = "https://api.rugcheck.xyz/v1/auth/login/solana"
) -> Optional[str]:
    if not private_key_hex or not public_key:
        logger.error("Private key or public key for RugCheck JWT generation is missing.")
        return None

    try:
        timestamp = int(time.time() * 1000)
        message_text = "Sign-in to Rugcheck.xyz"
        message_to_sign_bytes = message_text.encode('utf-8')

        try:
            seed_bytes = HexEncoder.decode(private_key_hex)
            if len(seed_bytes) != 32:
                logger.error(
                    f"Invalid private key length after hex decoding for RugCheck: {len(seed_bytes)} bytes. Expected 32 bytes (seed)."
                )
                return None
            signing_key = SigningKey(seed_bytes)
        except Exception as e:
            logger.error(f"Error initializing signing key for RugCheck (check private key format/length - expected 32-byte seed in hex): {e}")
            return None

        signed_message = signing_key.sign(message_to_sign_bytes)
        signature_bytes = signed_message.signature

        request_body = {
            "message": {
                "message": message_text,
                "publicKey": public_key,
                "timestamp": timestamp
            },
            "signature": {
                "data": list(signature_bytes),
                "type": "ed25519"
            },
            "wallet": public_key
        }

        headers = {"Content-Type": "application/json"}
        logger.debug(f"Attempting RugCheck JWT generation. URL: {auth_url}, Body: {json.dumps(request_body)}")

        async with session.post(auth_url, headers=headers, data=json.dumps(request_body), timeout=10) as response:
            response_text = await response.text()
            if response.status == 200:
                try:
                    response_data = json.loads(response_text)
                except json.JSONDecodeError:
                    logger.error(f"RugCheck.xyz auth response is not valid JSON. Status: 200, Response: {response_text}")
                    return None

                jwt_token = response_data.get("token")
                if jwt_token:
                    logger.info("Successfully obtained RugCheck.xyz JWT token.")
                    return jwt_token
                else:
                    logger.error(f"RugCheck.xyz auth response missing 'token' field. Status: 200, Data: {response_data}")
                    return None
            else:
                logger.error(
                    f"RugCheck.xyz auth failed. Status: {response.status}, Response: {response_text}"
                )
                if response.status == 404:
                    logger.warning("RugCheck.xyz auth endpoint (POST /auth/login/solana) returned 404. It might be inactive or changed.")
                elif response.status == 400:
                    logger.warning(f"RugCheck.xyz auth returned 400 - Bad Request. Check request body/signature. Response: {response_text}")
                elif response.status == 401 or response.status == 403:
                    logger.warning(f"RugCheck.xyz auth returned {response.status} - Unauthorized/Forbidden. Check credentials/signature. Response: {response_text}")
                return None

    except aiohttp.ClientError as e:
        logger.error(f"Network error during RugCheck.xyz JWT generation: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred during RugCheck.xyz JWT generation: {e}", exc_info=True)
        return None
```
