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
    - `RUGCHECK_API_ENDPOINT`: The base URL for the RugCheck.xyz API (e.g., default `https://api.rugcheck.xyz/v1/tokens`). Used to construct specific report URLs.
    - `RUGCHECK_API_KEY`: Your optional API key for RugCheck.xyz. Currently not strictly required for the `/report/summary` endpoint used by the bot, but can be set if you have one for potential future use or other endpoints.
    - `RUGCHECK_SCORE_THRESHOLD`: The minimum `scoreNormalised` (0-100, higher is generally better) a token must have from RugCheck.xyz. Tokens with a score *below* this are filtered (e.g., default `70`).
    - `RUGCHECK_CRITICAL_RISK_NAMES`: A comma-separated list of specific risk names (case-sensitive) that are considered critical deal-breakers. If a token's RugCheck report contains any of these risks, it will be filtered (e.g., default `"MutableMetadata,MintAuthorityEnabled,FreezeAuthorityEnabled,HighPrivilegedFunctions,Honeypot"`).

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
- **API Key**: The bot can be configured with an optional `RUGCHECK_API_KEY`. While the `/report/summary` endpoint might not strictly require it for basic access, providing a key (using the `X-API-Key` header) is good practice and may be necessary for higher rate limits or other API features.
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
    - Incorporate the sentiment score into the trading decision logic (e.g., avoiding tokens with very negative sentiment or prioritizing those with strong positive sentiment, combined with other indicators).

## Security

- Never share your private key
- Start with small position sizes
- Monitor the bot regularly
- Keep your system secure

## Disclaimer

This bot is for educational purposes only. Crypto trading carries significant risks. Always do your own research and never invest more than you can afford to lose.

## License

MIT License
