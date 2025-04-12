"""Telegram Bot for Token Analysis using Bubblemaps and CoinGecko APIs

This bot provides detailed token analysis including:
- Market data (price, volume, market cap)
- Decentralization metrics
- Token distribution visualization
- Top holder analysis

Usage:
1. Start the bot with /start
2. Send a contract address to analyze
3. Optionally specify chain (e.g., 0x... eth)

Supported chains: eth, bsc, ftm, avax, poly, arbi, base

Author: Tony Stalker
License: MIT
"""

import os
import logging
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
import json

# Configuration
load_dotenv()
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# API Settings
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == 'your_telegram_bot_token_here':
    raise ValueError("Please set the TELEGRAM_TOKEN environment variable in .env file")
BUBBLEMAPS_API_URL = "https://api-legacy.bubblemaps.io"
BUBBLEMAPS_APP_URL = "https://app.bubblemaps.io"
COINGECKO_API_URL = "https://api.coingecko.com/api/v3"

# Chain mappings for CoinGecko API
CHAIN_TO_PLATFORM = {
    'eth': 'ethereum',
    'bsc': 'binance-smart-chain',
    'ftm': 'fantom',
    'avax': 'avalanche',
    'poly': 'polygon-pos',
    'arbi': 'arbitrum-one',
    'base': 'base'
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command and show welcome message.
    
    Args:
        update: Telegram update object
        context: Callback context
    """
    welcome_message = (
        "👋 Welcome to the Bubblemaps Bot!\n\n"
        "Send me a token contract address and I'll analyze:\n"
        "- Token distribution visualization\n"
        "- Market data (price, volume, market cap)\n"
        "- Decentralization metrics\n"
        "- Top holder analysis\n\n"
        "Example: 0x... eth (or bsc, ftm, avax, etc)"
    )
    await update.message.reply_text(welcome_message)

async def get_market_data(contract_address: str, chain: str) -> dict:
    """Fetch token market data from CoinGecko API.
    
    Args:
        contract_address: Token contract address
        chain: Blockchain network (eth, bsc, etc)
        
    Returns:
        dict: Market data including price, market cap, volume, and 24h change
    """
    if chain not in CHAIN_TO_PLATFORM:
        logger.warning(f"Unsupported chain: {chain}")
        return {}
        
    platform = CHAIN_TO_PLATFORM[chain]
    async with aiohttp.ClientSession() as session:
        coin_url = f"{COINGECKO_API_URL}/coins/{platform}/contract/{contract_address}"
        try:
            async with session.get(coin_url) as response:
                if response.status != 200:
                    logger.error(f"CoinGecko API error: {response.status}")
                    return {}
                    
                coin_data = await response.json()
                market_data = coin_data.get('market_data', {})
                
                return {
                    'price': market_data.get('current_price', {}).get('usd'),
                    'market_cap': market_data.get('market_cap', {}).get('usd'),
                    'volume_24h': market_data.get('total_volume', {}).get('usd'),
                    'price_change_24h': market_data.get('price_change_percentage_24h')
                }
        except Exception as e:
            logger.error(f"Failed to fetch market data: {e}")
            return {}

async def get_token_info(contract_address: str, chain: str = 'eth') -> dict:
    """Fetch token information from Bubblemaps API.
    
    Args:
        contract_address: Token contract address
        chain: Blockchain network (eth, bsc, etc)
        
    Returns:
        dict: Combined token data including metadata and distribution info
        None: If token is not found or API error occurs
    """
    async with aiohttp.ClientSession() as session:
        # Fetch metadata
        metadata_url = f"{BUBBLEMAPS_API_URL}/map-metadata?token={contract_address}&chain={chain}"
        async with session.get(metadata_url) as response:
            if response.status != 200:
                logger.error(f"Metadata API error: {response.status}")
                return None
            metadata = await response.json()
            if metadata.get('status') != 'OK':
                logger.error("Invalid metadata response")
                return None

        # Fetch distribution data
        data_url = f"{BUBBLEMAPS_API_URL}/map-data?token={contract_address}&chain={chain}"
        async with session.get(data_url) as response:
            if response.status != 200:
                logger.error(f"Data API error: {response.status}")
                return None
            token_data = await response.json()
            if token_data.get('status') != 'OK':
                logger.error("Invalid token data response")
                return None
                
            token_data['top_holders'] = [{
                'address': node['address'],
                'percentage': node['percentage'],
                'amount': node['amount'],
                'is_contract': node['is_contract'],
                'name': node.get('name', 'Unknown')
            } for node in nodes[:5]]
            
            # Get metadata information
            token_data['decentralization_score'] = metadata.get('decentralisation_score')
            identified_supply = metadata.get('identified_supply', {})
            token_data['percent_in_cexs'] = identified_supply.get('percent_in_cexs')
            token_data['contract_holder_percentage'] = identified_supply.get('percent_in_contracts')
            token_data['last_update'] = metadata.get('dt_update')
            
            # Calculate token metrics
            token_data['holder_count'] = len(nodes)  # Total holders
            token_data['whale_count'] = sum(1 for n in nodes if n['percentage'] > 1)  # Big holders with >1%
            
            # Calculate transaction flow
            links = legacy_data.get('links', [])
            total_flow = sum(link['forward'] + link['backward'] for link in links)
            token_data['total_flow'] = total_flow
            
            # Calculate a decentralization score (0-100)
            # A higher score means the token is more evenly distributed
            # We look at three things:
            # 1. How much do the biggest holders own? (Less is better, up to 50 points)
            # 2. How many different holders are there? (More is better, up to 30 points)
            # 3. How much is in smart contracts? (Less is better, up to 20 points)
            score = (
                max(0, 50 - (token_data.get('top_holders', [])[0]['percentage'] / 2)) +    # Up to 50 points for distribution
                min(30, len(nodes) / 5) +                      # Up to 30 points for number of holders
                max(0, 20 - (token_data.get('contract_holder_percentage', 0) / 5))         # Up to 20 points for low contract holdings
            )
            token_data['decentralization_score'] = min(100, round(score))
            
            return token_data

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
    """Processes a user's request to analyze a token and sends back the results"""
    # Get the contract address from the message
    message_parts = update.message.text.strip().split()
    if len(message_parts) < 1:
        await update.message.reply_text(
            "❌ Please provide a valid contract address.\n"
            f"Format: <contract_address> <chain>"
        )
        return
    
    contract_address = message_parts[0].lower()
    chain = message_parts[1].lower() if len(message_parts) > 1 else 'eth'
    
    # Basic validation of the contract address
    if not contract_address.startswith('0x') or len(contract_address) != 42:
        await update.message.reply_text(
            "❌ Invalid contract address format.\n"
            f"Format: <contract_address> <chain>"
        )
        return
    
    # Show processing message
    processing_message = await update.message.reply_text("🔍 Analyzing token... Please wait.")
    
    try:
        # Get token information and market data concurrently
        token_info, market_data = await asyncio.gather(
            get_token_info(contract_address, chain),
            get_market_data(contract_address, chain)
        )
        
        if not token_info:
            await processing_message.edit_text("❌ Invalid contract address or token not found on Bubblemaps.")
            return
        
        # Merge market data into token info
        token_info.update(market_data)
        
        # Capture bubble map
        screenshot_path = await capture_bubblemap(contract_address, chain)
        
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
        
        analysis += f"\n🔗 View on Bubblemaps: {BUBBLEMAPS_APP_URL}/{chain}/token/{contract_address}"
        
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
        await processing_message.edit_text("❌ An error occurred while processing your request. Please try again later.")

def main():
    """Sets up and starts the Telegram bot"""
    # Create a new bot with our token
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Tell the bot what to do with different types of messages
    application.add_handler(CommandHandler("start", start))  # Handle /start command
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_contract_address))  # Handle contract addresses

    # Start listening for messages
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot stopped due to error: {e}", exc_info=True)