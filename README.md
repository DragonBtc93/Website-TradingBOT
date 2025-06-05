# Solana Trading Bot

An automated trading bot for Solana tokens with real-time monitoring and analysis capabilities.

## Features

- Real-time token scanning and analysis
- Advanced technical analysis indicators
- Automated trading with risk management features (Stop Loss, Take Profit)
- **Trailing Stop Loss**: Dynamically adjusts the stop-loss price upwards as the token price increases.
- **Targeted Market Cap Scanning**: Initiates detailed analysis only when a token's market cap reaches a configurable target (`TARGET_MARKET_CAP_TO_SCAN`), with an overall max (`MAX_MARKET_CAP`).
- **Token Safety Check (RugCheck.xyz Integration)**: Queries the RugCheck.xyz API for token risk assessment and filters out tokens based on score and critical warnings.
- **Social Media Sentiment (Placeholder)**: Simulates social media sentiment analysis; results are logged but not yet used for filtering.
- Web-based dashboard (if applicable, or specify if it's CLI based)
- Integration with Jupiter aggregator for best swap rates (for trade execution)
- Multiple take-profit levels
- Position management


## Setup

1. Clone the repository
2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and configure your settings:
```bash
cp .env.example .env
```

4. Edit `.env` with your configuration.

   **Important Security Notice: Managing Your `WALLET_PRIVATE_KEY`**

   Your `WALLET_PRIVATE_KEY` is extremely sensitive. It provides full control over your Solana wallet.
   - **Never hardcode your private key directly in any script or share it publicly.**
   - The bot is configured to load `WALLET_PRIVATE_KEY` from an environment variable stored in the `.env` file. This file is listed in `.gitignore` and should never be committed to version control.

   **To set up your `WALLET_PRIVATE_KEY`:**
   - Open the `.env` file you created in the previous step.
   - Find the line `WALLET_PRIVATE_KEY=""`.
   - Replace the empty string with your actual Solana wallet private key. For example:
     ```
     WALLET_PRIVATE_KEY=your_actual_private_key_here
     ```
   - Save the `.env` file.

- Adjust other trading parameters as needed
- Configure risk management settings, including:
  - `STOP_LOSS_PERCENTAGE`: Standard stop-loss percentage from entry price.
  - `TRAILING_STOP_LOSS_PERCENTAGE`: Percentage for the trailing stop-loss feature (e.g., `5` for 5%).
  - `MAX_POSITION_SIZE`: Maximum percentage of portfolio to allocate to a single trade.
  - `TAKE_PROFIT_LEVELS`: Define multiple levels for taking profit.
  - `TARGET_MARKET_CAP_TO_SCAN`: The minimum market capitalization (FDV) a token must reach for detailed analysis (e.g., `30000`).

  - **RugCheck.xyz Configuration:**
    - `RUGCHECK_API_ENDPOINT`: The base URL for the RugCheck.xyz API (default: `https://api.rugcheck.xyz/v1/tokens`). Used to construct specific report URLs.
    - `RUGCHECK_API_KEY`: Optional. Your static API key or a pre-obtained JWT for RugCheck.xyz. If provided, this may be used directly for authentication (e.g., in an `X-API-Key` header or `Authorization: Bearer {JWT}` if it's a JWT). If this is set, dynamic JWT generation using the private key below might be skipped. Default: `""`.
    - `RUGCHECK_AUTH_SOLANA_PRIVATE_KEY`: Optional. The hex-encoded 32-byte seed of a Solana private key dedicated for RugCheck.xyz JWT generation. **EXTREMELY SENSITIVE - HANDLE WITH UTMOST CARE.** If this and the public key below are provided, the bot will attempt to generate a JWT for RugCheck API authentication. Default: `""`.
    - `RUGCHECK_AUTH_WALLET_PUBLIC_KEY`: Optional. The Solana public key (wallet address as a string) corresponding to `RUGCHECK_AUTH_SOLANA_PRIVATE_KEY`. Required if dynamic JWT generation is used. Default: `""`.
    - `RUGCHECK_SCORE_THRESHOLD`: The minimum `scoreNormalised` (0-100, where higher is generally better, e.g., less risky) a token must achieve from RugCheck.xyz. Tokens with a score *below* this threshold will be filtered out. Default: `10`.
    - `RUGCHECK_CRITICAL_RISK_NAMES`: A comma-separated list of specific risk names (case-sensitive) identified by RugCheck.xyz that are considered critical deal-breakers by this bot. If a token's report contains any of these risk names, it will be filtered out. Default: `"Honeypot,RugpullHistory,ProxyContract,UnverifiedSourceCode,MintAuthorityEnabled,FreezeAuthorityEnabled,MutableMetadata,HighPrivilegedFunctions"`.

## Running the Bot

Start the bot and web interface:
```bash
python main.py
```

Access the dashboard at `http://localhost:8000`

## Trading Strategy

The bot implements a comprehensive trading strategy:

1. Token Scanning:
- Monitors new token pairs on Solana, primarily using data from DexScreener.
- **Market Cap Based Filtering**:
    - Initially checks if a token's market capitalization (FDV - Fully Diluted Valuation) meets the `TARGET_MARKET_CAP_TO_SCAN` defined in the configuration. Detailed analysis is only performed if it meets this threshold.
    - Further ensures the market cap does not exceed `MAX_MARKET_CAP`, an upper limit to avoid tokens that are already too large.
- Analyzes liquidity, transaction volume, and patterns for tokens that pass the market cap criteria.
- Performs safety checks (see "Token Safety Check" section).
- Placeholder for social sentiment analysis (see "Social Media Sentiment" section).
- The old "Validates contract security" point is now covered by the more detailed "Token Safety Check" section.

2. Entry Criteria:
- Token age < 24 hours
- Minimum liquidity threshold
- Healthy buy/sell ratio
- Volume spike detection
- Technical indicator confirmation

3. Position Management:
- Multiple take-profit levels (2x, 3x, 5x, 10x)
- Trailing stop-loss
- Position sizing based on portfolio
- Risk management rules

4. Exit Strategy:
- Automated profit taking
- Stop-loss enforcement
- Technical indicator based exits
- Whale movement monitoring

### Trailing Stop Loss
This feature helps to lock in profits while a trade is performing well and protect against sudden downturns. Here's how it works:
- When a position is opened, an initial stop-loss is set based on `STOP_LOSS_PERCENTAGE`.
- A `highest_price_since_entry` is tracked for the position.
- If the current price of the token moves above this `highest_price_since_entry`, the record is updated.
- A new potential stop-loss price, the "trailing stop price," is calculated as `highest_price_since_entry * (1 - TRAILING_STOP_LOSS_PERCENTAGE / 100.0)`.
- The actual stop-loss for the position is then adjusted to be the maximum of its current value and this new `trailing_stop_price`. This means the stop-loss price can only move up, never down.
- This helps protect gains by raising the stop-loss level as the price increases, but keeping it fixed if the price dips temporarily (unless the dip hits the current stop-loss).
- The `TRAILING_STOP_LOSS_PERCENTAGE` can be configured in your `.env` file.

### Token Safety Check (RugCheck.xyz Integration)
To enhance security and reduce the risk of trading malicious tokens, the bot integrates with the [RugCheck.xyz](https://rugcheck.xyz/) API.
- **Functionality**: For each token that passes initial scanning criteria (like market cap), the bot queries the RugCheck.xyz API endpoint `RUGCHECK_API_ENDPOINT/{token_address}/report/summary`.
- **Filtering Logic**: A token is deemed unsafe and filtered out if ANY of the following conditions are met, based on the API response and your configuration:
    - **Score Threshold**: If the token's `scoreNormalised` (a 0-100 score from RugCheck, where higher is generally better) is *less than* the `RUGCHECK_SCORE_THRESHOLD` defined in your configuration.
    - **Critical Risks**: If any risk reported by the API has a `name` that matches one of the names listed in your `RUGCHECK_CRITICAL_RISK_NAMES` configuration.
    - **API Call Failure**: If the API call fails, returns an error, or the response cannot be parsed, the token is typically treated as unsafe by default.
- **Logging**: Detailed reasons for failing the safety check (e.g., low score, specific critical risks found) are logged. Passed checks are also logged with key metrics like the `scoreNormalised`.
- **Authentication and API Key Usage**:
    - The bot supports authenticated requests to RugCheck.xyz, which may be necessary for higher rate limits or accessing certain endpoints.
    - **JWT Generation (Primary Method)**: If `RUGCHECK_AUTH_SOLANA_PRIVATE_KEY` (hex-encoded 32-byte seed) and `RUGCHECK_AUTH_WALLET_PUBLIC_KEY` are provided in your `.env` file, the bot will attempt to dynamically generate a JSON Web Token (JWT). This process involves:
        1.  Signing a standard message ("Sign-in to Rugcheck.xyz") along with a timestamp using your configured Solana private key.
        2.  Sending this signature and public key to the RugCheck.xyz authentication endpoint (typically `https://api.rugcheck.xyz/v1/auth/login/solana`).
        3.  If successful, RugCheck.xyz returns a JWT. This JWT is then used for subsequent API requests in the `Authorization: Bearer {JWT}` header.
    - **Static API Key/JWT (Fallback/Alternative)**: You can also provide a static API key or a pre-obtained JWT via the `RUGCHECK_API_KEY` environment variable.
        - If `RUGCHECK_API_KEY` is set, it will be used directly (assumed to be a JWT for `Authorization: Bearer` header, unless RugCheck.xyz specifies a different usage for static keys like `X-API-Key`). Dynamic JWT generation will be skipped if this is present.
    - **Unauthenticated Access**: If neither a static `RUGCHECK_API_KEY` nor the pair `RUGCHECK_AUTH_SOLANA_PRIVATE_KEY`/`RUGCHECK_AUTH_WALLET_PUBLIC_KEY` are provided, API requests will be made without authentication. This may lead to stricter rate limits or limited access.

    > **IMPORTANT SECURITY NOTICE: `RUGCHECK_AUTH_SOLANA_PRIVATE_KEY`**
    >
    > - The `RUGCHECK_AUTH_SOLANA_PRIVATE_KEY` is an EXTREMELY SENSITIVE piece of information.
    > - It grants control over the corresponding Solana wallet address (`RUGCHECK_AUTH_WALLET_PUBLIC_KEY`).
    > - **NEVER share this private key.**
    > - **NEVER commit it to version control (e.g., Git).** Ensure your `.env` file (where you store this key) is listed in your `.gitignore` file.
    > - Use a dedicated, low-value "burner" wallet for this authentication if possible, not your main trading or personal wallet.
    > - Secure the environment where this key is stored. Unauthorized access to this key can lead to loss of funds from the associated wallet.

- **Filtering Logic Clarification**:
    - In addition to the score and general critical risks, the default configuration for `RUGCHECK_CRITICAL_RISK_NAMES` now explicitly includes `"MintAuthorityEnabled"` and `"FreezeAuthorityEnabled"`. This means if RugCheck.xyz reports that a token still has an active mint or freeze authority, it will typically be flagged as unsafe and filtered out by the bot, unless you modify this list.
- **Note**: The effectiveness of this filter depends on the accuracy of the RugCheck.xyz API and the configured `RUGCHECK_SCORE_THRESHOLD` and `RUGCHECK_CRITICAL_RISK_NAMES`. These parameters should be set according to your risk tolerance. The interpretation of scores and risk names from RugCheck.xyz is based on their API documentation (e.g., their Swagger spec).

### Social Media Sentiment (Placeholder)
Understanding the social media sentiment around a token can provide additional trading insights.
- **Functionality**: The bot includes a placeholder function that simulates fetching social media sentiment for a token.
- **Current Status**: This feature is currently a **placeholder**.
    - It returns a predefined, neutral sentiment score (e.g., `{'sentiment_score': 0.5, 'sentiment': 'neutral', 'source': 'placeholder'}`).
    - The information is logged when a potential token is being processed.
- **Future Work (`TODO`):**
    - Integrate with actual social media APIs (e.g., Twitter/X API, Reddit API) or sentiment analysis services (e.g., LunarCrush, Santiment).
    - Implement NLP (Natural Language Processing) techniques to analyze fetched text data and generate a sentiment score.
    - Incorporate the sentiment score into the trading decision logic (e.g., avoiding tokens with very negative sentiment or prioritizing those with strong positive sentiment, combined with other 
