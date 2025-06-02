import os
from dotenv import load_dotenv
import ast

# Load environment variables
load_dotenv()

# Solana configuration
SOLANA_NETWORK = "mainnet-beta"
SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"
WALLET_PRIVATE_KEY = os.getenv("WALLET_PRIVATE_KEY")

# Token scanning parameters
MIN_LIQUIDITY = 25000
MAX_MARKET_CAP = 750000
MIN_TRANSACTIONS = 75
MAX_TOKEN_AGE_HOURS = 6

# Risk management
STOP_LOSS_PERCENTAGE = 12
TRAILING_STOP_LOSS_PERCENTAGE = 5 # Percentage below highest price to set trailing stop
MAX_POSITION_SIZE = 0.03
TAKE_PROFIT_LEVELS = [1.5, 2, 3, 5]

# Technical analysis parameters
VOLUME_SPIKE_THRESHOLD = 2.5
MIN_BUY_SELL_RATIO = 0.65
CONSOLIDATION_PERIOD = 10

# Advanced filters
MIN_HOLDER_COUNT = 100
MAX_WALLET_CONCENTRATION = 10
MIN_LP_LOCKED_PERCENTAGE = 80

# API endpoints
DEXSCREENER_API = "https://api.dexscreener.com/latest/dex"
JUPITER_API = "https://quote-api.jup.ag/v1"
