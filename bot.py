import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import aiohttp
import json

# Load environment variables
load_dotenv()

# Set up logging so we can track what's happening with our bot
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Important settings for our bot
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')  # Your bot's unique identifier
BUBBLEMAPS_LEGACY_URL = "https://api-legacy.bubblemaps.io"  # Where we get token data from

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Says hello and explains what the bot can do when someone starts a chat"""
    welcome_message = (
        "👋 Welcome to the Bubblemaps Bot!\n\n"
        "I can help you analyze any token supported by Bubblemaps. "
        "Just send me a contract address, and I'll provide:\n"
        "- Token bubble map visualization\n"
        "- Market information\n"
        "- Decentralization score\n"
        "- Additional insights\n\n"
        "Try it now by sending a contract address!"
    )
    await update.message.reply_text(welcome_message)

async def get_token_info(contract_address: str, chain: str = 'eth') -> dict:
    """Gets all the important information about a token, like who owns it and how it's distributed"""
    async with aiohttp.ClientSession() as session:
        # First, let's get the token's data from Bubblemaps
        legacy_url = f"{BUBBLEMAPS_LEGACY_URL}/map-data?token={contract_address}&chain={chain}"
        async with session.get(legacy_url) as response:
            if response.status != 200:
                return None
                
            legacy_data = await response.json()
            token_data = {
                'symbol': legacy_data.get('symbol'),
                'full_name': legacy_data.get('full_name'),
                'is_nft': legacy_data.get('is_X721', False)
            }
            
            # Get detailed holder information
            nodes = legacy_data.get('nodes', [])
            if not nodes:
                return None
                
            token_data['top_holders'] = [{
                'address': node['address'],
                'percentage': node['percentage'],
                'amount': node['amount'],
                'is_contract': node['is_contract'],
                'name': node.get('name', 'Unknown')
            } for node in nodes[:5]]
            
            # Let's count some important numbers about the token
            token_data['holder_count'] = len(nodes)  # How many people hold this token
            token_data['whale_count'] = sum(1 for n in nodes if n['percentage'] > 1)  # Big holders with >1%
            
            # Figure out how much is held by smart contracts vs regular wallets
            contract_holders = [n for n in nodes if n.get('is_contract', False)]
            contract_percentage = sum(h['percentage'] for h in contract_holders)
            token_data['contract_holder_percentage'] = contract_percentage
            
            # Calculate how actively the token is being traded
            links = legacy_data.get('links', [])
            total_flow = sum(link['forward'] + link['backward'] for link in links)
            token_data['total_flow'] = total_flow
            
            # Check if the token is concentrated in a few hands
            top_holder_percentage = sum(n['percentage'] for n in nodes[:3])
            token_data['top_holder_percentage'] = top_holder_percentage
            
            # Calculate a decentralization score (0-100)
            # A higher score means the token is more evenly distributed
            # We look at three things:
            # 1. How much do the biggest holders own? (Less is better, up to 50 points)
            # 2. How many different holders are there? (More is better, up to 30 points)
            # 3. How much is in smart contracts? (Less is better, up to 20 points)
            score = (
                max(0, 50 - (top_holder_percentage / 2)) +    # Up to 50 points for distribution
                min(30, len(nodes) / 5) +                      # Up to 30 points for number of holders
                max(0, 20 - (contract_percentage / 5))         # Up to 20 points for low contract holdings
            )
            token_data['decentralization_score'] = min(100, round(score))
            
            return token_data

async def capture_bubblemap(contract_address: str) -> str:
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
        url = f"https://bubblemaps.io/token/{contract_address}"
        logger.info(f"Loading URL: {url}")
        driver.get(url)
        logger.info("Waiting for page to load...")
        driver.implicitly_wait(10)
        
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
    # Split the message into contract address and blockchain (e.g., 'eth', 'bsc')
    message_parts = update.message.text.strip().split()
    contract_address = message_parts[0]
    chain = message_parts[1] if len(message_parts) > 1 else 'eth'  # Default to Ethereum if not specified
    
    # Make sure they specified a valid blockchain
    valid_chains = ['eth', 'bsc', 'ftm', 'avax', 'cro', 'arbi', 'poly', 'base', 'sol', 'sonic']
    if chain not in valid_chains:
        await update.message.reply_text(
            f"❌ Invalid chain. Please use one of: {', '.join(valid_chains)}"
            f"\nFormat: <contract_address> <chain>"
        )
        return
    
    # Show processing message
    processing_message = await update.message.reply_text("🔍 Analyzing token... Please wait.")
    
    try:
        # Get token information
        token_info = await get_token_info(contract_address, chain)
        if not token_info:
            await processing_message.edit_text("❌ Invalid contract address or token not found on Bubblemaps.")
            return
        
        # Capture bubble map
        screenshot_path = await capture_bubblemap(contract_address)
        
        # Prepare analysis message
        token_type = "NFT Collection" if token_info.get('is_nft') else "Token"
        # Format numeric values safely
        market_cap = token_info.get('marketCap')
        price = token_info.get('price')
        volume = token_info.get('volume24h')
        holder_count = token_info.get('holder_count')
        whale_count = token_info.get('whale_count')
        contract_holdings = token_info.get('contract_holder_percentage')
        total_flow = token_info.get('total_flow')

        analysis = (
            f"📊 {token_type} Analysis for {token_info.get('full_name', 'Unknown')} ({token_info.get('symbol', 'N/A')})\n\n"
            f"💰 Market Cap: ${market_cap:,.2f if isinstance(market_cap, (int, float)) else 'N/A'}\n"
            f"💵 Price: ${price:,.8f if isinstance(price, (int, float)) else 'N/A'}\n"
            f"📈 24h Volume: ${volume:,.2f if isinstance(volume, (int, float)) else 'N/A'}\n\n"
            f"🎯 Decentralization Metrics:\n"
            f"└ Score: {token_info.get('decentralization_score', 'N/A')}/100\n"
            f"└ Total Holders: {holder_count:,d if isinstance(holder_count, int) else holder_count}\n"
            f"└ Whale Holders: {whale_count}\n"
            f"└ Cluster Count: {token_info.get('cluster_count', 'N/A')}\n"
            f"└ Contract Holdings: {contract_holdings:.1f if isinstance(contract_holdings, (int, float)) else 'N/A'}%\n"
            f"└ Transaction Flow: {total_flow:,.0f if isinstance(total_flow, (int, float)) else 'N/A'}\n\n"
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
        
        analysis += f"\n🔗 View on Bubblemaps: https://bubblemaps.io/token/{contract_address}"
        
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
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()