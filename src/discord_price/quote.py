import asyncio
import aiohttp
import time
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass
from functools import lru_cache

logger = logging.getLogger(__name__)

@dataclass
class CryptoQuote:
    symbol: str
    name: str
    slug: str
    price_usd: float
    percent_change_1h: float
    percent_change_24h: float
    percent_change_7d: float
    market_cap: float
    volume_24h: float
    last_updated: str

class PriceQuoteCache:
    def __init__(self, api_key: str, cache_ttl: int = 300, max_cache_size: int = 1000):
        self.api_key = api_key
        self.cache_ttl = cache_ttl
        self.max_cache_size = max_cache_size
        self.cache: Dict[str, Dict] = {}
        self.session: Optional[aiohttp.ClientSession] = None
        self.quotes_endpoint = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
        self.last_request_time = 0
        self.min_request_interval = 1.0
    
    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={
                    'X-CMC_PRO_API_KEY': self.api_key,
                    'Accept': 'application/json',
                    'Accept-Encoding': 'deflate, gzip'
                }
            )
        return self.session
    
    def _generate_cache_key(self, symbols: List[str]) -> str:
        return ','.join(sorted(symbols))
    
    def _is_cache_valid(self, cache_entry: Dict, current_time: float) -> bool:
        return (current_time - cache_entry['timestamp']) < self.cache_ttl
    
    def _cleanup_cache(self):
        current_time = time.time()
        # Remove expired entries
        expired_keys = [k for k, v in self.cache.items() if not self._is_cache_valid(v, current_time)]
        for key in expired_keys:
            del self.cache[key]
        
        # Enforce size limit
        if len(self.cache) > self.max_cache_size:
            sorted_items = sorted(self.cache.items(), key=lambda x: x[1]['timestamp'])
            for key, _ in sorted_items[:len(self.cache) - self.max_cache_size]:
                del self.cache[key]
    
    async def _rate_limit(self):
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            await asyncio.sleep(self.min_request_interval - time_since_last)
        self.last_request_time = time.time()
    
    async def _fetch_from_api(self, symbols: List[str]) -> List[CryptoQuote]:
        await self._rate_limit()
        session = await self._get_session()
        
        try:
            async with session.get(self.quotes_endpoint, params={'symbol': ','.join(symbols), 'convert': 'USD'}) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_api_response(data)
                elif response.status == 429:
                    logger.warning("API rate limit hit")
                    await asyncio.sleep(60)
                    raise Exception("Rate limit exceeded")
                else:
                    error_text = await response.text()
                    logger.error(f"API request failed: {response.status} - {error_text}")
                    raise Exception(f"API request failed: {response.status}")
        except aiohttp.ClientError as e:
            logger.error(f"Network error: {e}")
            raise Exception(f"Network error: {e}")
    
    def _parse_api_response(self, data: Dict) -> List[CryptoQuote]:
        quotes = []
        try:
            for symbol, info in data.get('data', {}).items():
                quote_data = info.get('quote', {}).get('USD', {})
                quotes.append(CryptoQuote(
                    symbol=info.get('symbol', ''),
                    name=info.get('name', ''),
                    slug=info.get('slug', ''),
                    price_usd=float(quote_data.get('price', 0)),
                    percent_change_1h=float(quote_data.get('percent_change_1h', 0)),
                    percent_change_24h=float(quote_data.get('percent_change_24h', 0)),
                    percent_change_7d=float(quote_data.get('percent_change_7d', 0)),
                    market_cap=float(quote_data.get('market_cap', 0)),
                    volume_24h=float(quote_data.get('volume_24h', 0)),
                    last_updated=quote_data.get('last_updated', '')
                ))
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Error parsing API response: {e}")
            raise Exception(f"Failed to parse API response: {e}")
        return quotes
    
    async def fetch(self, symbols: List[str], current_time: float) -> List[CryptoQuote]:
        if not symbols:
            return []
        
        self._cleanup_cache()
        cache_key = self._generate_cache_key(symbols)
        
        # Check cache
        if cache_key in self.cache and self._is_cache_valid(self.cache[cache_key], current_time):
            return self.cache[cache_key]['data']
        
        # Fetch from API
        try:
            quotes = await self._fetch_from_api(symbols)
            self.cache[cache_key] = {'data': quotes, 'timestamp': current_time}
            return quotes
        except Exception as e:
            # Return stale cache if available
            if cache_key in self.cache:
                logger.warning(f"Using stale cache: {e}")
                return self.cache[cache_key]['data']
            logger.error(f"No cache available: {e}")
            return []
    
    async def fetch_no_cache(self, symbols: List[str]) -> List[CryptoQuote]:
        return await self._fetch_from_api(symbols) if symbols else []
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
        self.cache.clear()

@lru_cache(maxsize=128)
def format_price(price: float) -> str:
    if price < 0.01:
        return f"${price:.6f}"
    elif price < 1:
        return f"${price:.4f}"
    elif price < 1000:
        return f"${price:.2f}"
    else:
        return f"${price:.0f}"
