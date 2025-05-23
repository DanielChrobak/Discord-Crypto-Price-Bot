from typing import Optional, List, Dict
from dataclasses import dataclass, field
import json
import logging
from .utils import to_all_strings, to_all_ints

logger = logging.getLogger(__name__)

# Data storage files
DATA_FILE = "crypto_bot_data.json"
STYLES_FILE = "crypto_bot_styles.json"

# Default styles structure
default_styles = {
    "price_up_icon": "📈",
    "price_down_icon": "📉",
}

@dataclass
class GuildConfiguration:
    id: int
    update_category: Optional[int] = None
    voice_tickers: List[str] = field(default_factory=list)
    ratio_tickers: Dict[str, int] = field(default_factory=dict)
    message_tickers: Dict[str, int] = field(default_factory=dict)
    management_role_id: Optional[int] = None
    cmc_api_key: Optional[str] = None

@dataclass
class Configuration:
    guilds: Dict[int, GuildConfiguration]

def config_from_dict(d: Dict) -> Configuration:
    """Produce a bot configuration struct from a dictionary loaded from JSON"""
    guilds: Dict[int, GuildConfiguration] = {}
    
    for guild_id_s, guild_data in d.items():
        guild_id = int(guild_id_s)
        update_category = guild_data.get('update_category')
        if update_category is not None:
            update_category = int(update_category)
        
        management_role_id = guild_data.get('management_role_id')
        if management_role_id is not None:
            management_role_id = int(management_role_id)
        
        voice_tickers = guild_data.get('voice_tickers', [])
        ratio_tickers = to_all_ints(guild_data.get('ratio_tickers', {}))
        message_tickers = to_all_ints(guild_data.get('message_tickers', {}))
        cmc_api_key = guild_data.get('cmc_api_key')
        
        guilds[guild_id] = GuildConfiguration(
            id=guild_id,
            update_category=update_category,
            voice_tickers=voice_tickers,
            ratio_tickers=ratio_tickers,
            message_tickers=message_tickers,
            management_role_id=management_role_id,
            cmc_api_key=cmc_api_key,
        )
    
    return Configuration(guilds=guilds)

def dict_from_config(c: Configuration) -> Dict:
    """Produce a JSON-compatible dictionary from a server configuration"""
    d = {}
    for guild in c.guilds.values():
        guild_data = {
            'message_tickers': to_all_strings(guild.message_tickers),
            'ratio_tickers': to_all_strings(guild.ratio_tickers),
            'voice_tickers': guild.voice_tickers,
        }
        
        if guild.update_category is not None:
            guild_data['update_category'] = str(guild.update_category)
        
        if guild.management_role_id is not None:
            guild_data['management_role_id'] = str(guild.management_role_id)
        
        if guild.cmc_api_key is not None:
            guild_data['cmc_api_key'] = guild.cmc_api_key
        
        d[str(guild.id)] = guild_data
    
    return d

def load_styles() -> dict:
    """Load style data from JSON or give reasonable defaults"""
    data = dict(default_styles)
    data.update(load_json(STYLES_FILE))
    return data

def load_config() -> Configuration:
    """Load bot data from JSON or give reasonable defaults"""
    data = load_json(DATA_FILE)
    return config_from_dict(data)

def load_json(path: str) -> dict:
    """Load data from JSON file or fail quietly and return empty dict"""
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_config(c: Configuration):
    """Save configuration to JSON file"""
    d = dict_from_config(c)
    with open(DATA_FILE, 'w') as f:
        json.dump(d, f, indent=4)
