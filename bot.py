import os
import sys
import logging
import asyncio
import json
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
import time
from webdriver_manager.chrome import ChromeDriverManager

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

def debug_api_response(name, data, level="info"):
    """Log API response data in a readable format"""
    logger.info(f"--- {name} API Response ---")
    if level == "debug":
        # For full data dumps
        logger.info(f"Full response: {json.dumps(data, indent=2)}")
    elif isinstance(data, dict):
        # For key information
        for key, value in data.items():
            if isinstance(value, dict):
                logger.info(f"{key}: {json.dumps(value, indent=2)}")
            else:
                logger.info(f"{key}: {value}")
    else:
        logger.info(f"Data: {data}")
    logger.info("------------------------")

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
        logger.warning(f"Unsupported chain: {chain}")
        return {}
        
    platform = CHAIN_TO_PLATFORM[chain]
    url = f"{COINGECKO_API_URL}/coins/{platform}/contract/{addr}"
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=15) as resp:
                if resp.status != 200:
                    logger.warning(f"CoinGecko API returned status {resp.status} for {addr}")
                    return {}
                
                data = await resp.json()
                market = data.get('market_data', {})
                result = {
                    'price': market.get('current_price', {}).get('usd'),
                    'market_cap': market.get('market_cap', {}).get('usd'),
                    'volume_24h': market.get('total_volume', {}).get('usd'),
                    'price_change_24h': market.get('price_change_percentage_24h')
                }
                
                return result
                
        except asyncio.TimeoutError:
            logger.error(f"Timeout getting market data for {addr}")
            return {}
        except Exception as e:
            logger.error(f"Market data error: {e}", exc_info=True)
            return {}

async def get_token_info(addr: str, chain: str = 'eth') -> dict:
    """Fetch token info from Bubblemaps."""
    logger.info(f"Fetching token info for {addr} on {chain}")
    
    async with aiohttp.ClientSession() as session:
        try:
            # Get metadata
            meta_url = f"{BUBBLEMAPS_API_URL}/map-metadata?token={addr}&chain={chain}"
            async with session.get(meta_url, timeout=15) as resp:
                if resp.status != 200:
                    logger.warning(f"Bubblemaps metadata API returned status {resp.status} for {addr}")
                    return None
                meta = await resp.json()
                if meta.get('status') != 'OK':
                    logger.warning(f"Bubblemaps metadata status: {meta.get('status')}, message: {meta.get('message')}")
                    return None
            
            # Get data
            data_url = f"{BUBBLEMAPS_API_URL}/map-data?token={addr}&chain={chain}"
            async with session.get(data_url, timeout=15) as resp:
                if resp.status != 200:
                    logger.warning(f"Bubblemaps data API returned status {resp.status} for {addr}")
                    return None
                data = await resp.json()
            
            # Extract relevant fields
            result = {
                'full_name': data.get('full_name', 'Unknown'),
                'symbol': data.get('symbol', 'N/A'),
                'decentralization_score': meta.get('decentralisation_score'),
                'percent_in_cexs': meta.get('identified_supply', {}).get('percent_in_cexs'),
                'percent_in_contracts': meta.get('identified_supply', {}).get('percent_in_contracts'),
                'last_update': meta.get('dt_update', 'Unknown'),
                'is_nft': data.get('is_X721', False),
                'top_holders': data.get('nodes', [])[:5],
            }
            
            return result
        
        except Exception as e:
            logger.error(f"Error fetching token info: {e}", exc_info=True)
            return None

async def capture_bubblemap(contract_address: str, chain: str = 'eth') -> str:
    """Takes a picture of the token's bubble map visualization from the website"""
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    
    try:
        driver = webdriver.Chrome(ChromeDriverManager().install(), options=options)
        url = f"{BUBBLEMAPS_APP_URL}/{chain}/token/{contract_address}"
        logger.info(f"Loading URL: {url}")
        driver.get(url)
        logger.info("Waiting for 'bubblemaps-canvas' element to be present...")
        WebDriverWait(driver, 60).until(
            EC.presence_of_element_located((By.CLASS_NAME, "bubblemaps-canvas"))
        )
        logger.info("Element found, waiting for visualization to render...")
        await asyncio.sleep(10)  # Wait for rendering
        timestamp = int(time.time())
        screenshot_path = f"bubblemap_{contract_address}_{timestamp}.png"
        driver.save_screenshot(screenshot_path)
        logger.info(f"Screenshot saved: {screenshot_path}")
        return screenshot_path
    except Exception as e:
        logger.error(f"Error during screenshot capture: {e}", exc_info=True)
        raise
    finally:
        if 'driver' in locals():
            driver.quit()

async def handle_contract_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    processing_message = await update.message.reply_text("⏳ Processing your request...")
    
    try:
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
        
        logger.info(f"Processing token request: {addr} on {chain}")
        
        try:
            token_info = await get_token_info(addr, chain)
            market_data = await get_market_data(addr, chain)
        except Exception as e:
            logger.error(f"Data fetch error: {e}", exc_info=True)
            token_info, market_data = None, {}
        
        if token_info is None:
            await processing_message.edit_text("❌ Token not found or not supported on Bubblemaps")
            return
            
        screenshot_task = asyncio.create_task(capture_bubblemap(addr, chain))
        
        full_name = token_info.get('full_name', 'Unknown')
        symbol = token_info.get('symbol', 'N/A')
        is_nft = token_info.get('is_nft', False)
        token_type = "NFT Collection" if is_nft else "Token"
        
        analysis = f"📊 {token_type} Analysis for {full_name} ({symbol})\n\n"
        
        if market_data:
            price = market_data.get('price')
            market_cap = market_data.get('market_cap')
            volume_24h = market_data.get('volume_24h')
            price_change_24h = market_data.get('price_change_24h')
            
            analysis += "Market Data:\n"
            analysis += f"- Price: {format_number(price, is_price=True)}\n"
            analysis += f"- Market Cap: {format_number(market_cap)}\n"
            analysis += f"- 24h Volume: {format_number(volume_24h)}\n"
            if price_change_24h is not None:
                analysis += f"- 24h Change: {price_change_24h:+.2f}%\n"
            else:
                analysis += "- 24h Change: N/A\n"
            analysis += "\n"
        else:
            analysis += "Market Data: N/A\n\n"
        
        decentralization_score = token_info.get('decentralization_score')
        percent_in_cexs = token_info.get('percent_in_cexs')
        percent_in_contracts = token_info.get('percent_in_contracts')
        
        analysis += "Decentralization Metrics:\n"
        if decentralization_score is not None:
            analysis += f"- Score: {decentralization_score}/100\n"
        else:
            analysis += "- Score: N/A\n"
        if percent_in_cexs is not None:
            analysis += f"- Percent in CEXs: {percent_in_cexs:.1f}%\n"
        else:
            analysis += "- Percent in CEXs: N/A\n"
        if percent_in_contracts is not None:
            analysis += f"- Percent in Contracts: {percent_in_contracts:.1f}%\n"
        else:
            analysis += "- Percent in Contracts: N/A\n"
        analysis += "\n"
        
        analysis += "Top 5 Holders:\n"
        top_holders = token_info.get('top_holders', [])
        if top_holders:
            for idx, holder in enumerate(top_holders, 1):
                percentage = holder.get('percentage', 0)
                amount = holder.get('amount', 0)
                name = holder.get('name', 'Unknown')
                address = holder.get('address', 'Unknown')
                is_contract = holder.get('is_contract', False)
                contract_status = '📜' if is_contract else '👤'
                
                analysis += (
                    f"{idx}. {contract_status} {name}\n"
                    f"   └ {address[:8]}...{address[-4:]}\n"
                    f"   └ {percentage:.2f}% ({amount} tokens)\n"
                )
        else:
            analysis += "No holder data available\n"
        
        last_update = token_info.get('last_update')
        analysis += f"\nLast Update: {last_update}\n"
        
        analysis += f"\n🔗 View on Bubblemaps: {BUBBLEMAPS_APP_URL}/{chain}/token/{addr}"
        
        try:
            screenshot_path = await asyncio.wait_for(screenshot_task, timeout=60)
            await update.message.reply_photo(
                photo=open(screenshot_path, 'rb'),
                caption=analysis
            )
            os.remove(screenshot_path)
        except asyncio.TimeoutError:
            logger.error("Screenshot capture timed out")
            await update.message.reply_text(
                text=f"⚠️ Could not generate bubble map visualization\n\n{analysis}"
            )
        except Exception as e:
            logger.error(f"Screenshot error: {e}", exc_info=True)
            await update.message.reply_text(
                text=f"⚠️ Could not generate bubble map visualization\n\n{analysis}"
            )
        
        await processing_message.delete()
        logger.info("Request processing completed successfully")
        
    except Exception as e:
        logger.error(f"Error processing contract address: {e}", exc_info=True)
        if 'processing_message' in locals():
            await processing_message.edit_text("❌ An error occurred while processing your request. Please try again later.")
        else:
            await update.message.reply_text("❌ An error occurred while processing your request. Please try again later.")

def format_number(value, decimal_places=2, is_price=False):
    logger.info(f"Formatting number: {value}, is_price={is_price}")
    if value is None:
        return 'N/A'
    try:
        if is_price and value < 0.01:
            return f"${value:,.8f}"
        return f"${value:,.{decimal_places}f}"
    except (TypeError, ValueError) as e:
        logger.error(f"Error formatting number {value}: {e}")
        return 'N/A'

def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_contract_address))
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}", exc_info=True)
        sys.exit(1)