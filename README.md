# Bubblemaps Telegram Bot

A Telegram bot that provides token analysis using Bubblemaps API. Get instant access to bubble map visualizations, market data, and decentralization scores for any supported token.

## Features

- Generate and display token bubble map screenshots
- Provide key token metrics:
  - Market capitalization
  - Current price
  - 24-hour trading volume
  - Decentralization score
- Easy-to-use interface through Telegram

## Prerequisites

- Python 3.8+
- Chrome/Chromium browser (for Selenium)
- Telegram Bot Token (get from @BotFather)

## Installation

1. Clone the repository:
```bash
git clone [your-repo-url]
cd bubblemaps-telegram-bot
```

2. Install required packages:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file in the project root with your credentials:
```
TELEGRAM_TOKEN=your_telegram_bot_token
```

## Usage

1. Start the bot:
```bash
python bot.py
```

2. Open Telegram and search for your bot using its username

3. Start a conversation with the bot using the `/start` command

4. Send any supported token's contract address to get its analysis

## Example

Send a contract address to the bot:
```
0x1234...abcd
```

The bot will respond with:
- A screenshot of the token's bubble map
- Token information including market cap, price, and volume
- Decentralization score
- Direct link to view on Bubblemaps

## Error Handling

The bot includes robust error handling for:
- Invalid contract addresses
- Unsupported tokens
- API connection issues
- Screenshot generation failures

## Security Notes

- Never share your API keys or tokens
- The bot runs in headless mode for security
- All temporary files (screenshots) are automatically cleaned up

## Deployment

You can deploy this bot to Railway.app for 24/7 availability:

1. Create an account on [Railway.app](https://railway.app)

2. Install Railway CLI:
```bash
npm i -g @railway/cli
```

3. Login to Railway:
```bash
railway login
```

4. Create a new project:
```bash
railway init
```

5. Add your environment variables in Railway dashboard:
   - Go to your project settings
   - Add `TELEGRAM_TOKEN` with your bot token

6. Deploy your bot:
```bash
railway up
```

Your bot will now run 24/7 on Railway's infrastructure!

## Contributing

Feel free to submit issues and enhancement requests!
