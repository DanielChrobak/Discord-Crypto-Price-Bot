import discord
from discord import app_commands
import asyncio
import logging
import os
from dotenv import load_dotenv
from .config import load_config, load_styles
from .quote import PriceQuoteCache
from .commands import CommandHandler
from .updaters import VoiceChannelUpdater, MessageTickerUpdater

logger = logging.getLogger(__name__)

class CryptoPriceBot:
    def __init__(self, config, styles, price_quoter):
        self.config = config
        self.styles = styles
        self.price_quoter = price_quoter
        
        # Initialize Discord client
        intents = discord.Intents.default()
        self.client = discord.Client(intents=intents)
        self.tree = app_commands.CommandTree(self.client)
        
        # Initialize components
        self.voice_updater = VoiceChannelUpdater(self.client, self.config, self.styles, self.price_quoter)
        self.message_updater = MessageTickerUpdater(self.client, self.config, self.price_quoter)
        self.command_handler = CommandHandler(
            self.client, self.tree, self.config, self.price_quoter, 
            self.voice_updater, self.message_updater
        )
        
        self._setup_events()
        self.command_handler.register_commands()
    
    def _setup_events(self):
        @self.client.event
        async def on_ready():
            await self.tree.sync()
            logger.info(f"{self.client.user} ready.")
            
            # Start update loops
            self.client.loop.create_task(self.voice_updater.update_loop())
            self.client.loop.create_task(self.message_updater.update_loop())
        
        @self.client.event
        async def on_disconnect():
            logger.info(f"{self.client.user} disconnected.")
    
    def run(self, token: str):
        self.client.run(token, log_handler=None)

def main():
    """Main entry point for the bot."""
    # Configure logging
    logging.basicConfig(
        format='%(asctime)s.%(msecs)03d %(name)-6s:[%(levelname)-8s] %(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S',
        level=logging.INFO
    )
    
    load_dotenv()
    discord_token = os.getenv("DISCORD_BOT_TOKEN")
    
    if not discord_token:
        logger.error("Missing DISCORD_BOT_TOKEN environment variable")
        return
    
    # Initialize and run bot
    config = load_config()
    styles = load_styles()
    price_quoter = PriceQuoteCache("dummy_key")
    
    bot = CryptoPriceBot(config, styles, price_quoter)
    bot.run(discord_token)

if __name__ == "__main__":
    main()
