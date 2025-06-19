import os
from dotenv import load_dotenv
import ast
import logging # Added for logging within the helper

# Initialize logger for this module
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Helper function for environment variable loading with type casting
def get_env_var(var_name, default_value, cast_type=str):
    env_value_str = os.getenv(var_name)

    # Determine the string value to process: either from .env or the string representation of default_value
    # If env_value_str is None, we will process the default_value.
    # If default_value itself is None (for truly optional vars) and env var not set, return None.
    if env_value_str is None and default_value is None:
        return None

    value_to_process_str = str(default_value) if env_value_str is None else env_value_str

    try:
        if cast_type == bool:
            # Handles "true", "True", "false", "False" from env or default string.
            # If default_value was already a bool and env_value_str is None, this will correctly cast str(True) or str(False).
            return value_to_process_str.lower() == "true"

        if cast_type == list:
            # If env var was not set AND default_value is already a list, return default_value directly.
            if env_value_str is None and isinstance(default_value, list):
                return default_value
            # Otherwise, value_to_process_str is a string (from env or str(default_value) if default was not a list).
            # This string is then parsed.
            s_value = value_to_process_str
            if s_value.startswith('[') and s_value.endswith(']'): # Handles "['item1', 'item2']"
                return ast.literal_eval(s_value)
            else: # Handles "item1,item2" for list of strings
                return [item.strip() for item in s_value.split(',')]

        if cast_type == dict:
            if env_value_str is None and isinstance(default_value, dict):
                return default_value
            return ast.literal_eval(value_to_process_str) # Handles "{'key':'value'}"

        # For int, float, str - direct casting of the string value.
        return cast_type(value_to_process_str)

    except (ValueError, SyntaxError) as e:
        original_env_val_for_log = f"'{env_value_str}'" if env_value_str is not None else "(not set)"
        logger.warning(
            f"Warning: Could not parse env var '{var_name}' (raw value from env: {original_env_val_for_log}, "
            f"effective value processed: '{value_to_process_str}', target type: {cast_type.__name__}). "
            f"Using default: '{default_value}'. Error: {e}"
        )

        # If parsing the determined string (from env or default) failed,
        # and the original default_value was not a string, it means it was already typed.
        # Return it if it matches the cast_type, otherwise, it's a setup error.
        if not isinstance(default_value, str) and default_value is not None:
            if isinstance(default_value, cast_type):
                return default_value
            else:
                # This case should ideally not be reached if defaults are well-defined primitive types or correct string representations
                logger.error(f"FATAL: Default value '{default_value}' for '{var_name}' is of type {type(default_value).__name__} but expected {cast_type.__name__}, and parsing failed.")
                raise ValueError(f"Default value for {var_name} ('{default_value}') is not directly usable as type {cast_type.__name__} after primary parsing failure.")

        # If the default_value was a string and failed parsing above (e.g. default="notabool" for bool)
        # this indicates a misconfiguration of the default value itself.
        if isinstance(default_value, str):
             logger.error(f"FATAL: The string default value '{default_value}' for '{var_name}' could not be parsed to {cast_type.__name__}.")
             raise ValueError(f"The string default value for {var_name} ('{default_value}') is invalid for type {cast_type.__name__}.")

        # If default_value is None and we are here, it means env var was also None, which is handled at the start.
        # This is a fallback for any unhandled case, though it should be rare.
        return default_value


# Solana configuration
SOLANA_NETWORK = get_env_var("SOLANA_NETWORK", "mainnet-beta", str)
SOLANA_RPC_URL = get_env_var("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com", str)
WALLET_PRIVATE_KEY = get_env_var("WALLET_PRIVATE_KEY", None, str) # No default for private key

# Token scanning parameters
MIN_LIQUIDITY = get_env_var("MIN_LIQUIDITY", "25000", int)
MAX_MARKET_CAP = get_env_var("MAX_MARKET_CAP", "750000", int)
TARGET_MARKET_CAP_TO_SCAN = get_env_var("TARGET_MARKET_CAP_TO_SCAN", "30000", int)
MIN_TRANSACTIONS = get_env_var("MIN_TRANSACTIONS", "75", int)
MAX_TOKEN_AGE_HOURS = get_env_var("MAX_TOKEN_AGE_HOURS", "6", int)

# Risk management
STOP_LOSS_PERCENTAGE = get_env_var("STOP_LOSS_PERCENTAGE", "12.0", float)
TRAILING_STOP_LOSS_PERCENTAGE = get_env_var("TRAILING_STOP_LOSS_PERCENTAGE", "5.0", float)
MAX_POSITION_SIZE = get_env_var("MAX_POSITION_SIZE", "0.03", float)
TAKE_PROFIT_LEVELS = get_env_var("TAKE_PROFIT_LEVELS", "[1.5, 2.0, 3.0, 5.0]", list)

# Technical analysis parameters
VOLUME_SPIKE_THRESHOLD = get_env_var("VOLUME_SPIKE_THRESHOLD", "2.5", float)
MIN_BUY_SELL_RATIO = get_env_var("MIN_BUY_SELL_RATIO", "0.65", float)
# CONSOLIDATION_PERIOD removed

# Advanced filters
MIN_HOLDER_COUNT = get_env_var("MIN_HOLDER_COUNT", "100", int)
# MAX_WALLET_CONCENTRATION removed
# MIN_LP_LOCKED_PERCENTAGE removed

# API endpoints
DEXSCREENER_API = get_env_var("DEXSCREENER_API", "https://api.dexscreener.com/latest/dex", str)
JUPITER_API = get_env_var("JUPITER_API", "https://quote-api.jup.ag/v1", str)

# RugCheck.xyz Configuration
# STATIC_RUGCHECK_JWT: Optional pre-obtained JWT for RugCheck.xyz.
# If set, dynamic JWT generation (using private/public keys below) will be skipped.
STATIC_RUGCHECK_JWT = get_env_var("STATIC_RUGCHECK_JWT", None, str)
RUGCHECK_API_ENDPOINT = get_env_var("RUGCHECK_API_ENDPOINT", "https://api.rugcheck.xyz/v1/tokens", str)

# Score threshold for RugCheck (0-100 for score_normalised or score if former not available).
# Lower scores are better (safer). Tokens with a score strictly ABOVE this will be considered risky.
RUGCHECK_SCORE_THRESHOLD = get_env_var("RUGCHECK_SCORE_THRESHOLD", 10, int)

# Specific risk names considered critical. If any of these are present in a token's RugCheck report,
# it will be considered unsafe. Case-sensitive.
# Default is a comma-separated string, parsed by get_env_var into a list.
RUGCHECK_CRITICAL_RISK_NAMES = get_env_var(
    "RUGCHECK_CRITICAL_RISK_NAMES",
    "Honeypot,RugpullHistory,ProxyContract,UnverifiedSourceCode,MintAuthorityEnabled,FreezeAuthorityEnabled,MutableMetadata,HighPrivilegedFunctions",
    list
)

# Pump.fun Token Filtering
FILTER_FOR_PUMPFUN_ONLY = get_env_var("FILTER_FOR_PUMPFUN_ONLY", "true", bool)
PUMPFUN_ADDRESS_SUFFIX = get_env_var("PUMPFUN_ADDRESS_SUFFIX", "pump", str)

# Trader Specific Parameters
TRADER_MAX_POSITION_SIZE = get_env_var("TRADER_MAX_POSITION_SIZE", "0.1", float) # Max portion of wallet balance for a single trade
TRADER_DEFAULT_TAKE_PROFIT_PCT = get_env_var("TRADER_DEFAULT_TAKE_PROFIT_PCT", "0.15", float) # Default take profit % (e.g., 0.15 for 15%)

# Technical Analysis - MACD
MACD_FAST_PERIOD = get_env_var("MACD_FAST_PERIOD", "12", int)
MACD_SLOW_PERIOD = get_env_var("MACD_SLOW_PERIOD", "26", int)
MACD_SIGNAL_PERIOD = get_env_var("MACD_SIGNAL_PERIOD", "9", int)

# Technical Analysis - Bollinger Bands
BOLLINGER_WINDOW = get_env_var("BOLLINGER_WINDOW", "20", int)
BOLLINGER_STD_DEV = get_env_var("BOLLINGER_STD_DEV", "2", int)
# Note: STOP_LOSS_PERCENTAGE and TRAILING_STOP_LOSS_PERCENTAGE are already defined under Risk Management.

# RugCheck.xyz JWT Authentication (if needed for specific endpoints or higher rate limits)
# IMPORTANT: RUGCHECK_AUTH_SOLANA_PRIVATE_KEY is extremely sensitive. Handle with utmost care.
# These are intended for generating a JWT to authenticate with RugCheck.xyz, not for general wallet operations.
RUGCHECK_AUTH_SOLANA_PRIVATE_KEY = get_env_var("RUGCHECK_AUTH_SOLANA_PRIVATE_KEY", None, str)
RUGCHECK_AUTH_WALLET_PUBLIC_KEY = get_env_var("RUGCHECK_AUTH_WALLET_PUBLIC_KEY", None, str)


