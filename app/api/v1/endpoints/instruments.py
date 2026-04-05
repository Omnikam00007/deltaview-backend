import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.database import get_db
from app.db.crud_instrument import create_instrument, get_instrument_by_id, get_instrument_by_symbol, get_instruments, update_instrument
from app.models.user import User
from app.schemas.instrument import InstrumentCreate, InstrumentResponse, InstrumentUpdate
import yfinance as yf

router = APIRouter()


@router.get("/", response_model=List[InstrumentResponse])
async def list_instruments(
    search: str | None = Query(None, description="Search by symbol, name, or ISIN"),
    exchange: str | None = Query(None, description="Filter by exchange (NSE, BSE)"),
    segment: str | None = Query(None, description="Filter by segment (equity, fno, mf)"),
    sector: str | None = Query(None, description="Filter by sector"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search and list instruments."""
    return await get_instruments(db, search=search, exchange=exchange, segment=segment, sector=sector)


@router.get("/by-symbol/{symbol}", response_model=InstrumentResponse)
async def get_or_fetch_instrument_by_symbol(
    symbol: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get an instrument by symbol. If missing, auto-fetch from yfinance and create."""
    symbol = symbol.upper()
    
    # 1. Try to find it in the database exactly
    instrument = await get_instrument_by_symbol(db, symbol)
    if instrument:
        return instrument

    # 2. It's missing, try to fetch metadata from yfinance
    # Add .NS suffix if it's an Indian stock and has no suffix (common convention)
    yf_symbol = symbol + ".NS" if "." not in symbol else symbol
    
    try:
        ticker = yf.Ticker(yf_symbol)
        info = ticker.info
        
        # If shortName is missing, yfinance couldn't find it
        if "shortName" not in info:
            raise ValueError(f"Ticker {yf_symbol} not found on Yahoo Finance")
            
        # 3. Create it in the database
        # Determine segment based on quoteType
        qt = info.get("quoteType", "").lower()
        segment = "equity"
        if qt == "etf":
            segment = "etf"
        elif qt == "mutualfund":
            segment = "mf"
        
        create_data = InstrumentCreate(
            symbol=symbol,
            name=info.get("shortName") or info.get("longName") or symbol,
            exchange=info.get("exchange", "NSE"),
            segment=segment,
            sector=info.get("sector", "Other"),
            lot_size=1
        )
        
        return await create_instrument(db, create_data)
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Instrument '{symbol}' not found locally, and auto-fetch failed: {str(e)}"
        )


@router.get("/{instrument_id}", response_model=InstrumentResponse)
async def get_instrument(
    instrument_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific instrument by ID."""
    instrument = await get_instrument_by_id(db, instrument_id)
    if not instrument:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instrument not found")
    return instrument


@router.post("/", response_model=InstrumentResponse, status_code=status.HTTP_201_CREATED)
async def add_instrument(
    body: InstrumentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a new instrument to the master list."""
    return await create_instrument(db, body)


@router.patch("/{instrument_id}", response_model=InstrumentResponse)
async def patch_instrument(
    instrument_id: uuid.UUID,
    body: InstrumentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update instrument details."""
    instrument = await get_instrument_by_id(db, instrument_id)
    if not instrument:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instrument not found")
    return await update_instrument(db, instrument, body)
