import json
import logging
from typing import List

from fastapi import APIRouter, Depends
from redis.asyncio import Redis

from app.core.redis import get_redis
from app.schemas.market import MarketIndexResponse

logger = logging.getLogger(__name__)

router = APIRouter()

INDICES = [
    {"yahoo_symbol": "^NSEI", "name": "Nifty 50"},
    {"yahoo_symbol": "^BSESN", "name": "Sensex"},
    {"yahoo_symbol": "^INDIAVIX", "name": "India VIX"},
]

CACHE_KEY = "market:indices"
CACHE_TTL = 60  # seconds


async def _fetch_from_yahoo() -> List[dict]:
    """Fetch current index data from Yahoo Finance using yfinance."""
    import yfinance as yf

    results = []
    symbols = [idx["yahoo_symbol"] for idx in INDICES]

    try:
        tickers = yf.Tickers(" ".join(symbols))

        for idx_info in INDICES:
            sym = idx_info["yahoo_symbol"]
            try:
                ticker = tickers.tickers.get(sym)
                if ticker is None:
                    continue
                info = ticker.fast_info
                current = getattr(info, "last_price", None)
                prev_close = getattr(info, "previous_close", None)

                if current is None or prev_close is None:
                    continue

                change = round(current - prev_close, 2)
                change_pct = round((change / prev_close) * 100, 2) if prev_close else 0.0

                results.append({
                    "symbol": sym,
                    "name": idx_info["name"],
                    "value": round(current, 2),
                    "change": change,
                    "change_percent": change_pct,
                })
            except Exception as e:
                logger.warning("Failed to fetch %s: %s", sym, e)
                continue
    except Exception as e:
        logger.error("Yahoo Finance fetch failed: %s", e)

    return results


@router.get("/indices", response_model=List[MarketIndexResponse])
async def get_market_indices(
    redis: Redis = Depends(get_redis),
):
    """Return live Indian market index data (Nifty 50, Sensex, India VIX).
    Results are cached in Redis for 60 seconds."""

    # Try cache first
    cached = await redis.get(CACHE_KEY)
    if cached:
        return json.loads(cached)

    # Fetch fresh data
    data = await _fetch_from_yahoo()

    if data:
        await redis.setex(CACHE_KEY, CACHE_TTL, json.dumps(data))

    return data
