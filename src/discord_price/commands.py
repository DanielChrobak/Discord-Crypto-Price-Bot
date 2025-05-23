import discord
from discord import app_commands
import logging
from datetime import datetime
from .config import Configuration, GuildConfiguration, save_config
from .quote import PriceQuoteCache
from .permissions import is_server_admin, has_bot_management_permission, get_management_role_name

logger = logging.getLogger(__name__)

class CommandHandler:
    def __init__(self, client, tree, config, price_quoter, voice_updater, message_updater):
        self.client = client
        self.tree = tree
        self.config = config
        self.price_quoter = price_quoter
        self.voice_updater = voice_updater
        self.message_updater = message_updater
    
    def _get_or_create_guild(self, guild_id):
        """Get or create guild configuration"""
        guild = self.config.guilds.get(guild_id)
        if guild is None:
            guild = GuildConfiguration(id=guild_id)
            self.config.guilds[guild_id] = guild
        return guild
    
    async def _validate_api_key(self, api_key):
        """Validate CoinMarketCap API key"""
        test_quoter = PriceQuoteCache(api_key)
        try:
            test_data = await test_quoter.fetch_no_cache(["BTC"])
            return bool(test_data)
        except Exception:
            return False
        finally:
            await test_quoter.close()
    
    async def _validate_ticker(self, ticker, api_key):
        """Validate ticker exists on CoinMarketCap"""
        guild_quoter = PriceQuoteCache(api_key)
        try:
            crypto_data = await guild_quoter.fetch_no_cache([ticker])
            return bool(crypto_data)
        finally:
            await guild_quoter.close()
    
    def _check_permissions_and_api(self, interaction):
        """Check permissions and API key availability"""
        if not has_bot_management_permission(interaction, self.config):
            return "permissions"
        
        guild = self.config.guilds.get(interaction.guild_id)
        if not guild or not guild.cmc_api_key:
            return "api_key"
        
        return "ok"
    
    def register_commands(self):
        """Register all slash commands"""
        
        @self.tree.command(name="set_cmc_api_key", description="Set CoinMarketCap API key (Admin only)")
        async def set_cmc_api_key(interaction: discord.Interaction, api_key: str):
            if not is_server_admin(interaction):
                await interaction.response.send_message("Administrator permissions required.", ephemeral=True)
                return
            
            if not await self._validate_api_key(api_key):
                await interaction.response.send_message("Invalid API key.", ephemeral=True)
                return
            
            guild = self._get_or_create_guild(interaction.guild_id)
            guild.cmc_api_key = api_key
            save_config(self.config)
            
            await interaction.response.send_message("API key set successfully.", ephemeral=True)
        
        @self.tree.command(name="remove_cmc_api_key", description="Remove CoinMarketCap API key (Admin only)")
        async def remove_cmc_api_key(interaction: discord.Interaction):
            if not is_server_admin(interaction):
                await interaction.response.send_message("Administrator permissions required.", ephemeral=True)
                return
            
            guild = self.config.guilds.get(interaction.guild_id)
            if guild and guild.cmc_api_key:
                guild.cmc_api_key = None
                save_config(self.config)
                await interaction.response.send_message("API key removed.", ephemeral=True)
            else:
                await interaction.response.send_message("No API key set.", ephemeral=True)
        
        @self.tree.command(name="set_bot_management_role", description="Set bot management role (Admin only)")
        async def set_bot_management_role(interaction: discord.Interaction, role: discord.Role):
            if not is_server_admin(interaction):
                await interaction.response.send_message("Administrator permissions required.", ephemeral=True)
                return
            
            guild = self._get_or_create_guild(interaction.guild_id)
            guild.management_role_id = role.id
            save_config(self.config)
            
            await interaction.response.send_message(f"Management role set to **{role.name}**.", ephemeral=True)
        
        @self.tree.command(name="remove_bot_management_role", description="Remove bot management role (Admin only)")
        async def remove_bot_management_role(interaction: discord.Interaction):
            if not is_server_admin(interaction):
                await interaction.response.send_message("Administrator permissions required.", ephemeral=True)
                return
            
            guild = self.config.guilds.get(interaction.guild_id)
            if guild and guild.management_role_id:
                old_role = discord.utils.get(interaction.guild.roles, id=guild.management_role_id)
                role_name = old_role.name if old_role else "Unknown Role"
                guild.management_role_id = None
                save_config(self.config)
                await interaction.response.send_message(f"Removed **{role_name}** as management role.", ephemeral=True)
            else:
                await interaction.response.send_message("No management role set.", ephemeral=True)
        
        @self.tree.command(name="set_voice_update_category", description="Set voice channel category")
        async def set_voice_update_category(interaction: discord.Interaction, category_id: str):
            check = self._check_permissions_and_api(interaction)
            if check == "permissions":
                await interaction.response.send_message("Bot management permissions required.", ephemeral=True)
                return
            elif check == "api_key":
                await interaction.response.send_message("Set API key first with /set_cmc_api_key", ephemeral=True)
                return
            
            try:
                category_id = int(category_id)
                category = discord.utils.get(interaction.guild.categories, id=category_id)
                if not category:
                    await interaction.response.send_message("Category not found.", ephemeral=True)
                    return
                
                guild = self._get_or_create_guild(interaction.guild_id)
                guild.update_category = category_id
                guild.voice_tickers = []
                save_config(self.config)
                
                await interaction.response.send_message(f"Update category set to {category.name}", ephemeral=True)
            except ValueError:
                await interaction.response.send_message("Invalid category ID.", ephemeral=True)
        
        @self.tree.command(name="add_voice_ticker", description="Add voice channel ticker")
        async def add_voice_ticker(interaction: discord.Interaction, ticker: str):
            await interaction.response.defer(ephemeral=True)
            
            check = self._check_permissions_and_api(interaction)
            if check == "permissions":
                await interaction.followup.send("Bot management permissions required.", ephemeral=True)
                return
            elif check == "api_key":
                await interaction.followup.send("Set API key first with /set_cmc_api_key", ephemeral=True)
                return
            
            ticker = ticker.upper()
            guild = self.config.guilds.get(interaction.guild_id)
            
            if not guild.update_category:
                await interaction.followup.send("Set update category first with /set_voice_update_category", ephemeral=True)
                return
            
            if not await self._validate_ticker(ticker, guild.cmc_api_key):
                await interaction.followup.send(f"Ticker {ticker} not found.", ephemeral=True)
                return
            
            if ticker not in guild.voice_tickers:
                guild.voice_tickers.append(ticker)
                save_config(self.config)
                # Use the new optimized method to add just this ticker
                await self.voice_updater.add_voice_ticker(interaction.guild_id, ticker)
                await interaction.followup.send(f"Added {ticker} to voice updates.", ephemeral=True)
            else:
                await interaction.followup.send(f"{ticker} already tracked.", ephemeral=True)
        
        @self.tree.command(name="remove_voice_ticker", description="Remove voice channel ticker")
        async def remove_voice_ticker(interaction: discord.Interaction, ticker: str):
            if not has_bot_management_permission(interaction, self.config):
                await interaction.response.send_message("Bot management permissions required.", ephemeral=True)
                return
            
            ticker = ticker.upper()
            guild = self.config.guilds.get(interaction.guild_id)
            
            if guild and ticker in guild.voice_tickers:
                guild.voice_tickers.remove(ticker)
                save_config(self.config)
                # Use the new optimized method to remove just this ticker
                await self.voice_updater.remove_voice_ticker(interaction.guild_id, ticker)
                await interaction.response.send_message(f"Removed {ticker} from voice updates.", ephemeral=True)
            else:
                await interaction.response.send_message(f"{ticker} not tracked.", ephemeral=True)
        
        @self.tree.command(name="add_message_ticker", description="Add message ticker")
        async def add_message_ticker(interaction: discord.Interaction, ticker: str, channel_id: str):
            check = self._check_permissions_and_api(interaction)
            if check == "permissions":
                await interaction.response.send_message("Bot management permissions required.", ephemeral=True)
                return
            elif check == "api_key":
                await interaction.response.send_message("Set API key first with /set_cmc_api_key", ephemeral=True)
                return
            
            ticker = ticker.upper()
            guild = self.config.guilds.get(interaction.guild_id)
            
            try:
                channel_id = int(channel_id)
                if not self.client.get_channel(channel_id):
                    await interaction.response.send_message("Channel not found.", ephemeral=True)
                    return
                
                if not await self._validate_ticker(ticker, guild.cmc_api_key):
                    await interaction.response.send_message(f"Ticker {ticker} not found.", ephemeral=True)
                    return
                
                guild.message_tickers[ticker] = channel_id
                save_config(self.config)
                await interaction.response.send_message(f"Added {ticker} to <#{channel_id}>", ephemeral=True)
            except ValueError:
                await interaction.response.send_message("Invalid channel ID.", ephemeral=True)
        
        @self.tree.command(name="remove_message_ticker", description="Remove message ticker")
        async def remove_message_ticker(interaction: discord.Interaction, ticker: str):
            if not has_bot_management_permission(interaction, self.config):
                await interaction.response.send_message("Bot management permissions required.", ephemeral=True)
                return
            
            ticker = ticker.upper()
            guild = self.config.guilds.get(interaction.guild_id)
            
            if guild and ticker in guild.message_tickers:
                del guild.message_tickers[ticker]
                save_config(self.config)
                await interaction.response.send_message(f"Removed {ticker} from messages.", ephemeral=True)
            else:
                await interaction.response.send_message(f"{ticker} not tracked.", ephemeral=True)
        
        @self.tree.command(name="add_message_ratio_tickers", description="Add ratio ticker")
        async def add_message_ratio_tickers(interaction: discord.Interaction, ticker1: str, ticker2: str, channel_id: str):
            check = self._check_permissions_and_api(interaction)
            if check == "permissions":
                await interaction.response.send_message("Bot management permissions required.", ephemeral=True)
                return
            elif check == "api_key":
                await interaction.response.send_message("Set API key first with /set_cmc_api_key", ephemeral=True)
                return
            
            ticker1, ticker2 = ticker1.upper(), ticker2.upper()
            guild = self.config.guilds.get(interaction.guild_id)
            
            try:
                channel_id = int(channel_id)
                if not self.client.get_channel(channel_id):
                    await interaction.response.send_message("Channel not found.", ephemeral=True)
                    return
                
                # Validate both tickers
                guild_quoter = PriceQuoteCache(guild.cmc_api_key)
                try:
                    crypto_data = await guild_quoter.fetch_no_cache([ticker1, ticker2])
                    by_symbol = {quote.symbol: quote for quote in crypto_data}
                    if not (by_symbol.get(ticker1) and by_symbol.get(ticker2)):
                        await interaction.response.send_message("One or both tickers not found.", ephemeral=True)
                        return
                finally:
                    await guild_quoter.close()
                
                pair_key = f"{ticker1}:{ticker2}"
                guild.ratio_tickers[pair_key] = channel_id
                save_config(self.config)
                await interaction.response.send_message(f"Added {pair_key} to <#{channel_id}>", ephemeral=True)
            except ValueError:
                await interaction.response.send_message("Invalid channel ID.", ephemeral=True)
        
        @self.tree.command(name="remove_message_ratio_tickers", description="Remove ratio ticker")
        async def remove_message_ratio_tickers(interaction: discord.Interaction, ticker1: str, ticker2: str):
            if not has_bot_management_permission(interaction, self.config):
                await interaction.response.send_message("Bot management permissions required.", ephemeral=True)
                return
            
            pair_key = f"{ticker1.upper()}:{ticker2.upper()}"
            guild = self.config.guilds.get(interaction.guild_id)
            
            if guild and pair_key in guild.ratio_tickers:
                del guild.ratio_tickers[pair_key]
                save_config(self.config)
                await interaction.response.send_message(f"Removed {pair_key} from ratios.", ephemeral=True)
            else:
                await interaction.response.send_message(f"Ratio {pair_key} not tracked.", ephemeral=True)
        
        # Force update commands
        @self.tree.command(name="force_update_tickers", description="Force update voice channels")
        async def force_update_tickers(interaction: discord.Interaction):
            check = self._check_permissions_and_api(interaction)
            if check == "permissions":
                await interaction.response.send_message("Bot management permissions required.", ephemeral=True)
                return
            elif check == "api_key":
                await interaction.response.send_message("Set API key first with /set_cmc_api_key", ephemeral=True)
                return
            
            await interaction.response.send_message("Updating voice channels...", ephemeral=True)
            await self.voice_updater.update_voice_channels_for_guild(interaction.guild_id)
        
        @self.tree.command(name="force_update_message_tickers", description="Force update message tickers")
        async def force_update_message_tickers(interaction: discord.Interaction):
            check = self._check_permissions_and_api(interaction)
            if check == "permissions":
                await interaction.response.send_message("Bot management permissions required.", ephemeral=True)
                return
            elif check == "api_key":
                await interaction.response.send_message("Set API key first with /set_cmc_api_key", ephemeral=True)
                return
            
            await interaction.response.send_message("Updating message tickers...", ephemeral=True)
            await self.message_updater.update_message_tickers_for_guild(interaction.guild_id, True, False)
        
        @self.tree.command(name="force_update_ratio_tickers", description="Force update ratio tickers")
        async def force_update_ratio_tickers(interaction: discord.Interaction):
            check = self._check_permissions_and_api(interaction)
            if check == "permissions":
                await interaction.response.send_message("Bot management permissions required.", ephemeral=True)
                return
            elif check == "api_key":
                await interaction.response.send_message("Set API key first with /set_cmc_api_key", ephemeral=True)
                return
            
            await interaction.response.send_message("Updating ratio tickers...", ephemeral=True)
            await self.message_updater.update_message_tickers_for_guild(interaction.guild_id, False, True)
        
        @self.tree.command(name="show_settings", description="Show bot settings")
        async def show_settings(interaction: discord.Interaction):
            if not has_bot_management_permission(interaction, self.config):
                await interaction.response.send_message("Bot management permissions required.", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="Crypto Bot Settings",
                description=f"Settings for {interaction.guild.name}",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            if self.client.user.avatar:
                embed.set_thumbnail(url=self.client.user.avatar.url)
            
            guild = self.config.guilds.get(interaction.guild_id)
            if not guild:
                embed.add_field(name="Status", value="No settings configured", inline=False)
                embed.add_field(name="Management Role", value="Not set", inline=False)
                embed.add_field(name="API Key", value="Not set", inline=False)
            else:
                # Add fields
                embed.add_field(name="Management Role", value=get_management_role_name(interaction, self.config), inline=False)
                embed.add_field(name="API Key", value="✅ Set" if guild.cmc_api_key else "❌ Not set", inline=False)
                
                if guild.update_category:
                    category = discord.utils.get(interaction.guild.categories, id=guild.update_category)
                    category_name = category.name if category else "Unknown"
                    embed.add_field(name="Update Category", value=f"{category_name} ({guild.update_category})", inline=False)
                
                # Tickers
                embed.add_field(name="Voice Tickers", value=", ".join(guild.voice_tickers) or "None", inline=False)
                
                if guild.message_tickers:
                    msg_text = "\n".join([f"**{t}** → <#{c}>" for t, c in guild.message_tickers.items()])
                    embed.add_field(name="Message Tickers", value=msg_text, inline=False)
                else:
                    embed.add_field(name="Message Tickers", value="None", inline=False)
                
                if guild.ratio_tickers:
                    ratio_text = "\n".join([f"**{p}** → <#{c}>" for p, c in guild.ratio_tickers.items()])
                    embed.add_field(name="Ratio Tickers", value=ratio_text, inline=False)
                else:
                    embed.add_field(name="Ratio Tickers", value="None", inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
