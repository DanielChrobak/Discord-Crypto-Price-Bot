import discord
from .config import Configuration

def is_server_admin(interaction) -> bool:
    """Check if user has administrator permissions on the server"""
    return interaction.user.guild_permissions.administrator

def has_bot_management_permission(interaction, config: Configuration) -> bool:
    """
    Check if user can manage the bot - either server admin or has the custom management role
    """
    # Server administrators always have permission
    if is_server_admin(interaction):
        return True
    
    # Check if guild has a custom management role set
    guild_id = interaction.guild_id
    guild_config = config.guilds.get(guild_id)
    
    if guild_config and guild_config.management_role_id:
        # Check if user has the custom management role
        management_role = discord.utils.get(interaction.user.roles, id=guild_config.management_role_id)
        return management_role is not None
    
    return False

def get_management_role_name(interaction, config: Configuration) -> str:
    """Get the name of the management role for display purposes"""
    guild_id = interaction.guild_id
    guild_config = config.guilds.get(guild_id)
    
    if guild_config and guild_config.management_role_id:
        role = discord.utils.get(interaction.guild.roles, id=guild_config.management_role_id)
        if role:
            return role.name
        else:
            return "Unknown Role (may have been deleted)"
    
    return "Not set"
