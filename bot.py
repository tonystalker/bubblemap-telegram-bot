"""Telegram Bot for Token Analysis using Bubblemaps and CoinGecko APIs.

Provides token analysis including market data, decentralization metrics, and holder info.
Supported chains: eth, bsc, ftm, avax, poly, arbi, base

Usage: /start, then send contract address (e.g. 0x1234... eth)
"""

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
    logger.info(f"Fetching market data for {addr} on {platform}")
    
    async with aiohttp.ClientSession() as session:
        url = f"{COINGECKO_API_URL}/coins/{platform}/contract/{addr}"
        logger.info(f"CoinGecko API URL: {url}")
        
        try:
            # Add timeout to prevent hanging
            async with session.get(url, timeout=15) as resp:
                logger.info(f"CoinGecko API status: {resp.status}")
                
                if resp.status != 200:
                    logger.warning(f"CoinGecko API returned status {resp.status} for {addr}")
                    # Try to read error message if any
                    try:
                        error_text = await resp.text()
                        logger.warning(f"CoinGecko error response: {error_text[:200]}...")
                    except:
                        pass
                    return {}
                
                data = await resp.json()
                debug_api_response("CoinGecko", data, level="debug")
                
                # Extract market data
                market = data.get('market_data', {})
                result = {
                    'price': market.get('current_price', {}).get('usd'),
                    'market_cap': market.get('market_cap', {}).get('usd'),
                    'volume_24h': market.get('total_volume', {}).get('usd'),
                    'price_change_24h': market.get('price_change_percentage_24h')
                }
                
                logger.info(f"Extracted market data: {result}")
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
            # Get metadata with timeout
            meta_url = f"{BUBBLEMAPS_API_URL}/map-metadata?token={addr}&chain={chain}"
            logger.info(f"Bubblemaps metadata URL: {meta_url}")
            
            async with session.get(meta_url, timeout=15) as resp:
                logger.info(f"Bubblemaps metadata API status: {resp.status}")
                
                if resp.status != 200:
                    logger.warning(f"Bubblemaps metadata API returned status {resp.status} for {addr}")
                    # Try to read error message if any
                    try:
                        error_text = await resp.text()
                        logger.warning(f"Bubblemaps metadata error response: {error_text[:200]}...")
                    except:
                        pass
                    return None
                
                meta = await resp.json()
                debug_api_response("Bubblemaps Metadata", meta)
                
                if not meta:
                    logger.warning(f"Empty metadata response for {addr}")
                    return None
                    
            # Get data with timeout
            data_url = f"{BUBBLEMAPS_API_URL}/map-data?token={addr}&chain={chain}"
            logger.info(f"Bubblemaps data URL: {data_url}")
            
            async with session.get(data_url, timeout=15) as resp:
                logger.info(f"Bubblemaps data API status: {resp.status}")
                
                if resp.status != 200:
                    logger.warning(f"Bubblemaps data API returned status {resp.status} for {addr}")
                    # Try to read error message if any
                    try:
                        error_text = await resp.text()
                        logger.warning(f"Bubblemaps data error response: {error_text[:200]}...")
                    except:
                        pass
                    return None
                
                data = await resp.json()
                debug_api_response("Bubblemaps Data", data)
                
                if not data:
                    logger.warning(f"Empty data response for {addr}")
                    return None
                
                result = {
                    'name': meta.get('name', 'Unknown'),
                    'symbol': meta.get('symbol', 'N/A'),
                    'full_name': meta.get('name', 'Unknown'),
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
                
                logger.info(f"Extracted token info: {result}")
                return result
                    
        except asyncio.TimeoutError:
            logger.error(f"Timeout getting token info for {addr}")
            return None
        except Exception as e:
            logger.error(f"Token info error: {e}", exc_info=True)
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
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CLASS_NAME, "bubblemaps-canvas"))
            )
            # Additional wait to ensure visualization is rendered
            logger.info("Canvas element found, waiting for visualization to render...")
            await asyncio.sleep(10)  # Increased wait time for better rendering
        except Exception as e:
            logger.warning(f"Timeout or error waiting for elements: {e}")
            # Continue anyway - we'll try to take the screenshot
        
        # Save the bubble map as an image
        timestamp = int(time.time())
        screenshot_path = f"bubblemap_{contract_address}_{timestamp}.png"
        logger.info(f"Taking screenshot and saving to {screenshot_path}")
        driver.save_screenshot(screenshot_path)
        logger.info("Screenshot saved successfully")
        return screenshot_path
    except Exception as e:
        logger.error(f"Error during screenshot capture: {e}", exc_info=True)
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
        
        # Log the request
        logger.info(f"Processing token request: {addr} on {chain}")
        
        # Fetch data concurrently with extended timeout
        try:
            logger.info("Starting API data fetch")
            token_info_future = get_token_info(addr, chain)
            market_data_future = get_market_data(addr, chain)
            
            # Wait for both with individual error handling
            token_info = await token_info_future
            logger.info(f"Token info fetch completed: {'SUCCESS' if token_info else 'FAILED'}")
            
            market_data = await market_data_future
            logger.info(f"Market data fetch completed: {'SUCCESS' if market_data else 'FAILED'}")
            
        except Exception as e:
            logger.error(f"Data fetch error: {e}", exc_info=True)
            token_info, market_data = None, {}
        
        # Log the results
        logger.info(f"Token info: {token_info}")
        logger.info(f"Market data: {market_data}")
        
        # Check if we have at least basic token info
        if token_info is None:
            await processing_message.edit_text("❌ Token not found or not supported on Bubblemaps")
            return
            
        # Create combined data dictionary
        combined_data = {**token_info}
        if market_data:
            logger.info("Merging market data with token info")
            combined_data.update(market_data)
        
        # Log the combined data
        logger.info(f"Combined data: {combined_data}")
        
        # Start screenshot capture in the background
        logger.info("Starting screenshot capture task")
        screenshot_task = asyncio.create_task(capture_bubblemap(addr, chain))
        
        # Prepare analysis message
        token_type = "NFT Collection" if combined_data.get('is_nft') else "Token"
        # Get values from combined data
        market_cap = combined_data.get('market_cap')
        price = combined_data.get('price')
        volume = combined_data.get('volume_24h')
        price_change = combined_data.get('price_change_24h')
        holder_count = combined_data.get('holder_count')
        whale_count = combined_data.get('whale_count')
        cex_holdings = combined_data.get('percent_in_cexs')
        contract_holdings = combined_data.get('contract_holder_percentage')
        total_flow = combined_data.get('total_flow')
        decentralization_score = combined_data.get('decentralization_score')

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

        # Format percentages nicely
        def format_percent(value):
            logger.info(f"Formatting percentage: {value}")
            if value is None:
                return 'N/A'
            try:
                return f'{value:.1f}%'
            except (TypeError, ValueError) as e:
                logger.error(f"Error formatting percentage {value}: {e}")
                return 'N/A'

        # Format the last update time
        last_update = combined_data.get('last_update')
        if last_update:
            try:
                dt = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
                last_update_str = dt.strftime('%Y-%m-%d %H:%M UTC')
            except Exception as e:
                logger.error(f"Error formatting date {last_update}: {e}")
                last_update_str = 'Unknown'
        else:
            last_update_str = 'Unknown'

        logger.info("Building analysis text")
        analysis = (
            f"📊 {token_type} Analysis for {combined_data.get('full_name', 'Unknown')} ({combined_data.get('symbol', 'N/A')})\n\n"
            f"💰 Market Cap: {format_number(market_cap)}\n"
            f"💵 Price: {format_number(price, is_price=True)}\n"
            f"📈 24h Volume: {format_number(volume)}\n"
        )
        
        # Add price change only if it exists
        if price_change is not None:
            analysis += f"📊 24h Change: {price_change:+.2f}%\n\n"
        else:
            analysis += f"📊 24h Change: N/A\n\n"
            
        # Add decentralization metrics section
        analysis += f"🎯 Decentralization Metrics:\n"
        
        # Handle decentralization score specifically
        if decentralization_score is not None:
            analysis += f"└ Score: {decentralization_score}/100\n"
        else:
            analysis += f"└ Score: N/A/100\n"
            
        # Add other metrics
        analysis += (
            f"└ Total Holders: {f'{holder_count:,}' if isinstance(holder_count, int) else 'N/A'}\n"
            f"└ Whale Holders: {whale_count if whale_count is not None else 'N/A'}\n"
            f"└ CEX Holdings: {format_percent(cex_holdings)}\n"
            f"└ Contract Holdings: {format_percent(contract_holdings)}\n"
            f"└ Transaction Flow: {f'{total_flow:,.0f}' if isinstance(total_flow, (int, float)) else 'N/A'}\n"
            f"└ Last Update: {last_update_str}\n\n"
        )
        
        # Add top holders section
        analysis += f"Top 5 Holders:\n"
        
        # Add top holders information with names and contract status
        top_holders = combined_data.get('top_holders', [])
        if top_holders:
            for idx, holder in enumerate(top_holders, 1):
                try:
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
                except Exception as e:
                    logger.error(f"Error formatting holder {idx}: {e}")
                    analysis += f"{idx}. Error formatting holder data\n"
        else:
            analysis += "No holder data available\n"
        
        analysis += f"\n🔗 View on Bubblemaps: {BUBBLEMAPS_APP_URL}/{chain}/token/{addr}"
        
        # Wait for screenshot
        try:
            logger.info("Waiting for screenshot capture to complete")
            screenshot_path = await asyncio.wait_for(screenshot_task, timeout=30)
            
            # Send analysis and bubble map
            logger.info(f"Sending photo with analysis to user: {update.effective_user.id}")
            await update.message.reply_photo(
                photo=open(screenshot_path, 'rb'),
                caption=analysis
            )
            
            # Clean up
            try:
                os.remove(screenshot_path)
                logger.info(f"Removed screenshot file: {screenshot_path}")
            except Exception as e:
                logger.error(f"Error removing screenshot: {e}")
        except asyncio.TimeoutError:
            # If screenshot takes too long, send just the analysis
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