import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import aiohttp
import json

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Constants
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
BUBBLEMAPS_LEGACY_URL = "https://api-legacy.bubblemaps.io"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
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
    """Fetch token information from Bubblemaps Legacy API."""
    async with aiohttp.ClientSession() as session:
        # Get detailed data from legacy API
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
            
            # Calculate metrics
            token_data['holder_count'] = len(nodes)
            token_data['whale_count'] = sum(1 for n in nodes if n['percentage'] > 1)
            
            # Calculate contract vs non-contract holder distribution
            contract_holders = [n for n in nodes if n.get('is_contract', False)]
            contract_percentage = sum(h['percentage'] for h in contract_holders)
            token_data['contract_holder_percentage'] = contract_percentage
            
            # Get transaction flow data
            links = legacy_data.get('links', [])
            total_flow = sum(link['forward'] + link['backward'] for link in links)
            token_data['total_flow'] = total_flow
            
            # Calculate decentralization score based on distribution
            top_holder_percentage = sum(n['percentage'] for n in nodes[:3])
            token_data['top_holder_percentage'] = top_holder_percentage
            
            # Simple scoring algorithm:
            # - Lower top holder % is better (max 50 points)
            # - More holders is better (max 30 points)
            # - Lower contract % is better (max 20 points)
            score = (
                max(0, 50 - (top_holder_percentage / 2)) +  # 50 points max
                min(30, len(nodes) / 5) +                    # 30 points max
                max(0, 20 - (contract_percentage / 5))       # 20 points max
            )
            token_data['decentralization_score'] = min(100, round(score))
            
            return token_data

async def capture_bubblemap(contract_address: str) -> str:
    """Capture screenshot of the token's bubble map."""
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    try:
        # Load the bubble map page
        driver.get(f"https://bubblemaps.io/token/{contract_address}")
        driver.implicitly_wait(10)
        
        # Take screenshot
        screenshot_path = f"bubblemap_{contract_address}.png"
        driver.save_screenshot(screenshot_path)
        return screenshot_path
    finally:
        driver.quit()

async def handle_contract_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle contract address input and return analysis."""
    message_parts = update.message.text.strip().split()
    contract_address = message_parts[0]
    chain = message_parts[1] if len(message_parts) > 1 else 'eth'
    
    # Validate chain
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
        analysis = (
            f"📊 {token_type} Analysis for {token_info.get('full_name', 'Unknown')} ({token_info.get('symbol', 'N/A')})\n\n"
            f"💰 Market Cap: ${token_info.get('marketCap', 'N/A'):,.2f}\n"
            f"💵 Price: ${token_info.get('price', 'N/A'):,.8f}\n"
            f"📈 24h Volume: ${token_info.get('volume24h', 'N/A'):,.2f}\n\n"
            f"🎯 Decentralization Metrics:\n"
            f"└ Score: {token_info.get('decentralization_score', 'N/A')}/100\n"
            f"└ Total Holders: {token_info.get('holder_count', 'N/A'):,}\n"
            f"└ Whale Holders: {token_info.get('whale_count', 'N/A')}\n"
            f"└ Cluster Count: {token_info.get('cluster_count', 'N/A')}\n"
            f"└ Contract Holdings: {token_info.get('contract_holder_percentage', 'N/A'):.1f}%\n"
            f"└ Transaction Flow: {token_info.get('total_flow', 'N/A'):,.0f}\n\n"
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
        logger.error(f"Error processing contract address: {e}")
        await processing_message.edit_text("❌ An error occurred while processing your request. Please try again later.")

def main():
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_contract_address))

    # Start the Bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
