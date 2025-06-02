# Solana Trading Bot

An automated trading bot for Solana tokens with real-time monitoring and analysis capabilities.

## Features

- Real-time token scanning and analysis
- Advanced technical analysis indicators
- Automated trading with risk management features (Stop Loss, Take Profit)
- **Trailing Stop Loss**: Dynamically adjusts the stop-loss price upwards as the token price increases.
- Web-based dashboard (if applicable, or specify if it's CLI based)
- Integration with Jupiter aggregator for best swap rates (for trade execution)
- Multiple take-profit levels
- Position management
- **Token Safety Check (Placeholder)**: Attempts to query an external API (rugcheck.xyz - currently assumed) for token risk assessment. Results are logged.
- **Social Media Sentiment (Placeholder)**: Simulates social media sentiment analysis. Results are logged.


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

## Running the Bot

Start the bot and web interface:
```bash
python main.py
```

Access the dashboard at `http://localhost:8000`

## Trading Strategy

The bot implements a comprehensive trading strategy:

1. Token Scanning:
- Monitors new token launches
- Analyzes liquidity and volume
- Checks transaction patterns
- Validates contract security

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

### Token Safety Check (rugcheck.xyz - Placeholder)
To enhance security and avoid potentially malicious tokens, the bot includes a placeholder integration with an external token safety checking service.
- **Functionality**: Before considering a trade, the bot attempts to query an API endpoint (assumed to be `https://api.rugcheck.xyz/v1/solana/check/{token_address}`) for the base token of a potential pair.
- **Current Status**: This feature is currently a **placeholder**.
    - The API endpoint and its response structure are *assumed* and may not reflect the actual `rugcheck.xyz` API or any other similar service.
    - The bot logs the information received from this hypothetical API (e.g., risk level, warnings).
- **Future Work (`TODO`):**
    - Confirm a reliable API for token safety checks.
    - Adapt the parser to the actual API response structure.
    - Implement logic to filter or avoid tokens based on the safety assessment (e.g., skip tokens with a 'high' risk level).
- **Note**: No API key is currently assumed or required for this placeholder. If a real service is integrated, API key management will be necessary.

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
