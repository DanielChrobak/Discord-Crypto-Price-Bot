import logging
from discord_price.bot import CryptoPriceBot
from discord_price.config import load_config, load_styles
from discord_price.quote import PriceQuoteCache
import os
from dotenv import load_dotenv
import sys

# Configure logging
logformat = '%(asctime)s.%(msecs)03d %(name)-6s:[%(levelname)-8s] %(message)s'
logging.basicConfig(
    format=logformat,
    datefmt='%Y-%m-%dT%H:%M:%S',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

def main():
    # Load environment variables
    load_dotenv()
    
    # Get Discord token from .env file
    discord_token = os.getenv("DISCORD_BOT_TOKEN")
    
    if not discord_token:
        logger.error("Missing DISCORD_BOT_TOKEN environment variable")
        return
    
    # Initialize components
    config = load_config()
    styles = load_styles()
    
    # Create a dummy price quoter (won't be used since each guild has its own)
    price_quoter = PriceQuoteCache("dummy_key")
    
    # Create and run bot
    bot = CryptoPriceBot(config, styles, price_quoter)
    bot.run(discord_token)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Bot stopped by user")
        sys.exit(0)
    except Exception as e:
        logging.error(f"Bot crashed: {e}")
        sys.exit(1)