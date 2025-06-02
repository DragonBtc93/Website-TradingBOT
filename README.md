# Solana Trading Bot

An automated trading bot for Solana tokens with real-time monitoring and analysis capabilities.

## Features

- Real-time token scanning and analysis
- Advanced technical analysis indicators
- Automated trading with risk management
- Web-based dashboard
- Integration with Jupiter aggregator for best swap rates
- Multiple take-profit levels
- Trailing stop-loss
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
- Configure risk management settings

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

## Security

- Never share your private key
- Start with small position sizes
- Monitor the bot regularly
- Keep your system secure

## Disclaimer

This bot is for educational purposes only. Crypto trading carries significant risks. Always do your own research and never invest more than you can afford to lose.

## License

MIT License
