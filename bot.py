"""Telegram Bot for Token Analysis using Bubblemaps and CoinGecko APIs.

Provides token analysis including market data, decentralization metrics, and holder info.
Supported chains: eth, bsc, ftm, avax, poly, arbi, base

Usage: /start, then send contract address (e.g. 0x1234... eth)
"""

import os
import sys
import logging
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import aiohttp

# Configuration
load_dotenv()
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# API Settings
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN:
    raise ValueError("Please set TELEGRAM_TOKEN in .env file")
    
BUBBLEMAPS_API_URL = "https://api-legacy.bubblemaps.io"
BUBBLEMAPS_APP_URL = "https://app.bubblemaps.io"
COINGECKO_API_URL = "https://api.coingecko.com/api/v3"

# Chain mappings
CHAIN_TO_PLATFORM = {
    'eth': 'ethereum', 'bsc': 'binance-smart-chain', 'ftm': 'fantom',
    'avax': 'avalanche', 'poly': 'polygon-pos', 'arbi': 'arbitrum-one',
    'base': 'base'
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    await update.message.reply_text(
        "👋 Welcome! Send me a token contract address to analyze:\n"
        "• Token distribution & visualization\n"
        "• Market data & decentralization metrics\n"
        "• Top holder analysis\n\n"
        "Example: 0x1234... eth"
    )

async def get_market_data(addr: str, chain: str) -> dict:
    """Fetch token market data from CoinGecko."""
    if chain not in CHAIN_TO_PLATFORM:
        return {}
        
    platform = CHAIN_TO_PLATFORM[chain]
    async with aiohttp.ClientSession() as session:
        url = f"{COINGECKO_API_URL}/coins/{platform}/contract/{addr}"
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return {}
                data = await resp.json()
                market = data.get('market_data', {})
                return {
                    'price': market.get('current_price', {}).get('usd'),
                    'market_cap': market.get('market_cap', {}).get('usd'),
                    'volume_24h': market.get('total_volume', {}).get('usd'),
                    'price_change_24h': market.get('price_change_percentage_24h')
                }
        except Exception as e:
            logger.error(f"Market data error: {e}")
            return {}

async def get_token_info(addr: str, chain: str = 'eth') -> dict:
    """Fetch token info from Bubblemaps."""
    async with aiohttp.ClientSession() as session:
        try:
            # Get metadata
            meta_url = f"{BUBBLEMAPS_API_URL}/map-metadata?token={addr}&chain={chain}"
            async with session.get(meta_url) as resp:
                if resp.status != 200:
                    return None
                meta = await resp.json()
                if not meta:
                    return None
                    
            # Get data
            data_url = f"{BUBBLEMAPS_API_URL}/map-data?token={addr}&chain={chain}"
            async with session.get(data_url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if not data:
                    return None
                
                return {
                    'name': meta.get('name'),
                    'symbol': meta.get('symbol'),
                    'full_name': meta.get('name'),  # For consistency with the analysis function
                    'total_supply': meta.get('total_supply'),
                    'decentralization_score': data.get('decentralization_score'),
                    'percent_in_cexs': data.get('percent_in_cexs'),
                    'contract_holder_percentage': data.get('contract_holder_percentage'),
                    'total_flow': data.get('total_flow'),
                    'holder_count': data.get('holder_count'),
                    'whale_count': data.get('whale_count'),
                    'top_holders': data.get('top_holders', [])[:5],
                    'last_update': data.get('last_update'),
                    'is_nft': meta.get('is_nft', False)
                }
                    
        except Exception as e:
            logger.error(f"Token info error: {e}")
            return None

async def capture_bubblemap(contract_address: str, chain: str = 'eth') -> str:
    """Takes a picture of the token's bubble map visualization from the website"""
    # Set up Chrome options for headless mode
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    
    try:
        logger.info(f"Starting screenshot capture for {contract_address}")
        # Use Chrome directly, not the Remote WebDriver
        driver = webdriver.Chrome(options=options)
        
        # Visit the token's page and wait for it to load
        url = f"{BUBBLEMAPS_APP_URL}/{chain}/token/{contract_address}"
        logger.info(f"Loading URL: {url}")
        driver.get(url)
        logger.info("Waiting for page to load...")
        
        # Wait for specific elements to be visible
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "bubblemaps-canvas"))
            )
            # Additional wait to ensure visualization is rendered
            await asyncio.sleep(5)
        except Exception as e:
            logger.warning(f"Timeout waiting for elements: {e}")
        
        # Save the bubble map as an image
        screenshot_path = f"bubblemap_{contract_address}.png"
        logger.info(f"Taking screenshot and saving to {screenshot_path}")
        driver.save_screenshot(screenshot_path)
        logger.info("Screenshot saved successfully")
        return screenshot_path
    except Exception as e:
        logger.error(f"Error during screenshot capture: {e}")
        raise
    finally:
        # Always close the browser when we're done
        if 'driver' in locals():
            driver.quit()

async def handle_contract_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Send a processing message first
    processing_message = await update.message.reply_text("⏳ Processing your request...")
    
    try:
        # Parse input
        text = update.message.text.lower().strip()
        parts = text.split()
        
        if not parts:
            await processing_message.edit_text("❌ Please provide a contract address")
            return
            
        addr = parts[0]
        chain = parts[1] if len(parts) > 1 else 'eth'
        
        if not addr.startswith('0x') or len(addr) != 42:
            await processing_message.edit_text("❌ Invalid address format")
            return
            
        if chain not in CHAIN_TO_PLATFORM:
            await processing_message.edit_text(f"❌ Invalid chain. Supported: {', '.join(CHAIN_TO_PLATFORM.keys())}")
            return
        
        # Fetch data
        token_info, market_data = await asyncio.gather(
            get_token_info(addr, chain),
            get_market_data(addr, chain)
        )
        
        if token_info is None:
            await processing_message.edit_text("❌ Token not found or not supported")
            return
            
        # Merge market data into token info
        token_info.update(market_data or {})
        
        # Capture bubble map
        screenshot_path = await capture_bubblemap(addr, chain)
        
        # Prepare analysis message
        token_type = "NFT Collection" if token_info.get('is_nft') else "Token"
        # Get values from combined data
        market_cap = token_info.get('market_cap')
        price = token_info.get('price')
        volume = token_info.get('volume_24h')
        price_change = token_info.get('price_change_24h')
        holder_count = token_info.get('holder_count')
        whale_count = token_info.get('whale_count')
        contract_holdings = token_info.get('contract_holder_percentage')
        total_flow = token_info.get('total_flow')

        def format_number(value, decimal_places=2, is_price=False):
            if value is None:
                return 'N/A'
            try:
                if is_price:
                    return f"${value:,.8f}"
                return f"${value:,.{decimal_places}f}"
            except (TypeError, ValueError):
                return 'N/A'

        # Format percentages nicely
        def format_percent(value):
            if value is None:
                return 'N/A'
            return f'{value:.1f}%'

        # Format the last update time
        last_update = token_info.get('last_update')
        if last_update:
            try:
                dt = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
                last_update_str = dt.strftime('%Y-%m-%d %H:%M UTC')
            except:
                last_update_str = 'Unknown'
        else:
            last_update_str = 'Unknown'

        analysis = (
            f"📊 {token_type} Analysis for {token_info.get('full_name', 'Unknown')} ({token_info.get('symbol', 'N/A')})\n\n"
            f"💰 Market Cap: {format_number(market_cap)}\n"
            f"💵 Price: {format_number(price, is_price=True)}\n"
            f"📈 24h Volume: {format_number(volume)}\n"
            f"📊 24h Change: {f'{price_change:+.2f}%' if price_change else 'N/A'}\n\n"
            f"🎯 Decentralization Metrics:\n"
            f"└ Score: {token_info.get('decentralization_score', 'N/A')}/100\n"
            f"└ Total Holders: {f'{holder_count:,}' if isinstance(holder_count, int) else 'N/A'}\n"
            f"└ Whale Holders: {whale_count if whale_count is not None else 'N/A'}\n"
            f"└ CEX Holdings: {format_percent(token_info.get('percent_in_cexs'))}\n"
            f"└ Contract Holdings: {format_percent(token_info.get('contract_holder_percentage'))}\n"
            f"└ Transaction Flow: {f'{total_flow:,.0f}' if isinstance(total_flow, (int, float)) else 'N/A'}\n"
            f"└ Last Update: {last_update_str}\n\n"
            f"Top 5 Holders:\n"
        )
        
        # Add top holders information with names and contract status
        for idx, holder in enumerate(token_info.get('top_holders', []), 1):
            percentage = holder.get('percentage', 0)
            amount = holder.get('amount', 0)
            name = holder.get('name', 'Unknown')
            address = holder.get('address', 'Unknown')
            contract_status = '📜' if holder.get('is_contract') else '👤'
            
            analysis += (
                f"{idx}. {contract_status} {name}\n"
                f"   └ {address[:8]}...{address[-6:]}\n"
                f"   └ {percentage:.2f}% ({amount:,.0f} tokens)\n"
            )
        
        analysis += f"\n🔗 View on Bubblemaps: {BUBBLEMAPS_APP_URL}/{chain}/token/{addr}"
        
        # Send analysis and bubble map
        await update.message.reply_photo(
            photo=open(screenshot_path, 'rb'),
            caption=analysis
        )
        
        # Clean up
        os.remove(screenshot_path)
        await processing_message.delete()
        
    except Exception as e:
        logger.error(f"Error processing contract address: {e}", exc_info=True)
        if 'processing_message' in locals():
            await processing_message.edit_text("❌ An error occurred while processing your request. Please try again later.")
        else:
            await update.message.reply_text("❌ An error occurred while processing your request. Please try again later.")

def main():
    """Set up and run the bot without async/await."""
    # Create the Application
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_contract_address))
    
    # Run the bot until the user presses Ctrl-C
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}", exc_info=True)
        sys.exit(1)