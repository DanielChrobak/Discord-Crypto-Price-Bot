import asyncio
import time
import logging
import discord
from .config import Configuration
from .quote import PriceQuoteCache

logger = logging.getLogger(__name__)

class BaseUpdater:
    def __init__(self, client, config, price_quoter):
        self.client = client
        self.config = config
        self.price_quoter = price_quoter
    
    async def boundary_timer(self, cadence: int, name: str):
        now = time.time()
        next_boundary = cadence - (now % cadence)
        logger.info(f"Sleeping {next_boundary:.1f}s until next {name} boundary")
        await asyncio.sleep(next_boundary)
        
        while self.client.is_closed():
            logger.info(f"Retrying {name} update; client disconnected")
            await asyncio.sleep(180)

class VoiceChannelUpdater(BaseUpdater):
    def __init__(self, client, config, styles, price_quoter):
        super().__init__(client, config, price_quoter)
        self.styles = styles
    
    async def update_loop(self):
        logger.info("Voice update loop starting")
        await self.client.wait_until_ready()
        
        while True:
            await self.boundary_timer(3600, "voice update")
            await self.update_all_voice_channels()
    
    async def update_all_voice_channels(self):
        for guild_config in self.config.guilds.values():
            await self.update_voice_channels_for_guild(guild_config.id)
    
    def _format_price(self, price: float) -> str:
        """Format price based on its value"""
        if price < 0.01:
            return f"${price:.6f}"
        elif price < 1:
            return f"${price:.4f}"
        elif price < 1000:
            return f"${price:.2f}"
        else:
            return f"${price:.0f}"
    
    def _create_channel_name(self, quote) -> str:
        """Create channel name from quote data"""
        emoji = self.styles['price_up_icon' if quote.percent_change_1h >= 0 else 'price_down_icon']
        price_str = self._format_price(quote.price_usd)
        return f"{quote.symbol} {emoji} {price_str}"
    
    async def add_voice_ticker(self, guild_id: int, ticker: str):
        """Add a single voice ticker and create its channel"""
        guild_config = self.config.guilds.get(guild_id)
        if not (guild_config and guild_config.update_category and guild_config.cmc_api_key):
            return
        
        guild = self.client.get_guild(guild_id)
        if not guild:
            return
        
        category = discord.utils.get(guild.categories, id=guild_config.update_category)
        if not category:
            return
        
        guild_quoter = PriceQuoteCache(guild_config.cmc_api_key)
        try:
            # Get quotes for ALL tickers including the new one
            all_quotes = await guild_quoter.fetch(guild_config.voice_tickers, time.time())
            if not all_quotes:
                return
            
            # Sort all quotes by market cap (highest first)
            sorted_quotes = sorted(all_quotes, key=lambda x: x.market_cap, reverse=True)
            
            # Find the new ticker's quote and position
            new_quote = None
            target_position = 0
            
            for i, quote in enumerate(sorted_quotes):
                if quote.symbol == ticker:
                    new_quote = quote
                    target_position = i
                    break
            
            if not new_quote:
                return
            
            # Create the channel name
            channel_name = self._create_channel_name(new_quote)
            
            # Create the new channel at the end first
            new_channel = await category.create_voice_channel(name=channel_name)
            
            # Now move it to the correct position
            # We need to account for existing channels and find the right spot
            existing_channels = [ch for ch in category.voice_channels if ch.id != new_channel.id]
            
            # If we need to be at position 0, move to top
            if target_position == 0:
                await new_channel.edit(position=0)
            else:
                # Find the channel that should be right before us
                channels_before = target_position
                if channels_before < len(existing_channels):
                    # Move after the channel that should be before us
                    await new_channel.edit(position=existing_channels[channels_before - 1].position + 1)
                # If we're supposed to be at the end, we're already there
            
            logger.info(f"Added voice channel for {ticker} at position {target_position} in guild {guild_id}")
            
        finally:
            await guild_quoter.close()
    
    async def remove_voice_ticker(self, guild_id: int, ticker: str):
        """Remove a single voice ticker's channel"""
        guild_config = self.config.guilds.get(guild_id)
        if not (guild_config and guild_config.update_category):
            return
        
        guild = self.client.get_guild(guild_id)
        if not guild:
            return
        
        category = discord.utils.get(guild.categories, id=guild_config.update_category)
        if not category:
            return
        
        # Find and delete the channel for this ticker
        for channel in category.voice_channels:
            # Extract ticker symbol from channel name (format: "SYMBOL emoji $price")
            channel_parts = channel.name.split(' ')
            if channel_parts and channel_parts[0] == ticker:
                await channel.delete()
                logger.info(f"Removed voice channel for {ticker} in guild {guild_id}")
                break
    
    async def update_voice_channels_for_guild(self, guild_id: int):
        """Update voice channels for a specific guild - full refresh for scheduled updates"""
        guild_config = self.config.guilds.get(guild_id)
        if not (guild_config and guild_config.update_category and 
                guild_config.voice_tickers and guild_config.cmc_api_key):
            return
        
        guild = self.client.get_guild(guild_id)
        if not guild:
            logger.warning(f"Guild {guild_id} not found")
            return
        
        category = discord.utils.get(guild.categories, id=guild_config.update_category)
        if not category:
            return
        
        guild_quoter = PriceQuoteCache(guild_config.cmc_api_key)
        try:
            quotes = await guild_quoter.fetch(guild_config.voice_tickers, time.time())
            if not quotes:
                return
            
            # Get existing channels mapped by symbol
            existing_channels = {}
            for channel in category.voice_channels:
                channel_parts = channel.name.split(' ')
                if channel_parts:
                    symbol = channel_parts[0]
                    existing_channels[symbol] = channel
            
            # Sort quotes by market cap (highest first)
            sorted_quotes = sorted(quotes, key=lambda x: x.market_cap, reverse=True)
            
            # Track channels we've processed
            processed_channels = set()
            
            # Update existing channels and create new ones in correct order
            for i, quote in enumerate(sorted_quotes):
                channel_name = self._create_channel_name(quote)
                
                if quote.symbol in existing_channels:
                    # Update existing channel
                    existing_channel = existing_channels[quote.symbol]
                    
                    # Update name if needed
                    if existing_channel.name != channel_name:
                        await existing_channel.edit(name=channel_name)
                    
                    # Update position if needed
                    if existing_channel.position != i:
                        await existing_channel.edit(position=i)
                    
                    processed_channels.add(quote.symbol)
                else:
                    # Create new channel at correct position
                    await category.create_voice_channel(name=channel_name, position=i)
                    processed_channels.add(quote.symbol)
            
            # Delete channels for tickers that are no longer tracked
            for symbol, channel in existing_channels.items():
                if symbol not in processed_channels:
                    await channel.delete()
                    
        finally:
            await guild_quoter.close()

class MessageTickerUpdater(BaseUpdater):
    async def update_loop(self):
        logger.info("Message update loop starting")
        await self.client.wait_until_ready()
        
        while True:
            await self.boundary_timer(1800, "message")
            await self.update_all_message_tickers()
    
    async def update_all_message_tickers(self, do_regulars=True, do_ratios=True):
        for guild_config in self.config.guilds.values():
            await self.update_message_tickers_for_guild(guild_config.id, do_regulars, do_ratios)
    
    async def update_message_tickers_for_guild(self, guild_id: int, do_regulars=True, do_ratios=True):
        guild_config = self.config.guilds.get(guild_id)
        if not (guild_config and guild_config.cmc_api_key):
            return
        
        guild = self.client.get_guild(guild_id)
        if not guild:
            return
        
        guild_quoter = PriceQuoteCache(guild_config.cmc_api_key)
        try:
            if do_regulars:
                await self._update_regular_tickers(guild_config, guild_quoter)
            if do_ratios:
                await self._update_ratio_tickers(guild_config, guild_quoter)
        finally:
            await guild_quoter.close()
    
    async def _update_regular_tickers(self, guild_config, guild_quoter):
        if not guild_config.message_tickers:
            return
        
        symbols = list(guild_config.message_tickers.keys())
        quotes = await guild_quoter.fetch(symbols, time.time())
        quotes_by_symbol = {quote.symbol: quote for quote in quotes}
        
        for symbol, channel_id in guild_config.message_tickers.items():
            quote = quotes_by_symbol.get(symbol)
            if not quote:
                continue
            
            channel = self.client.get_channel(channel_id)
            if not channel:
                continue
            
            message = f"The price of {quote.name} ({symbol}) is ${quote.price_usd:.2f} USD on [CMC](<https://coinmarketcap.com/currencies/{quote.slug}/>)"
            await channel.send(message)
    
    async def _update_ratio_tickers(self, guild_config, guild_quoter):
        if not guild_config.ratio_tickers:
            return
        
        for pair, channel_id in guild_config.ratio_tickers.items():
            ticker1, ticker2 = pair.split(":")
            quotes = await guild_quoter.fetch([ticker1, ticker2], time.time())
            quotes_by_symbol = {quote.symbol: quote for quote in quotes}
            
            a, b = quotes_by_symbol.get(ticker1), quotes_by_symbol.get(ticker2)
            if not (a and b):
                continue
            
            channel = self.client.get_channel(channel_id)
            if not channel:
                continue
            
            ratio = int(b.price_usd / a.price_usd)
            message = f"The swap rate of {ticker1}:{ticker2} is {ratio}:1 on [CMC](<https://coinmarketcap.com/currencies/{a.slug}/>)"
            await channel.send(message)
