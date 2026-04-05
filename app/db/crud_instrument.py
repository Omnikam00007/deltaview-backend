import uuid
from typing import Sequence

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instrument import Instrument
from app.schemas.instrument import InstrumentCreate, InstrumentUpdate


async def create_instrument(db: AsyncSession, obj_in: InstrumentCreate) -> Instrument:
    db_obj = Instrument(
        symbol=obj_in.symbol.upper(),
        isin=obj_in.isin,
        name=obj_in.name,
        exchange=obj_in.exchange,
        segment=obj_in.segment,
        sector=obj_in.sector,
        lot_size=obj_in.lot_size,
    )
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


async def get_instruments(
    db: AsyncSession,
    search: str | None = None,
    exchange: str | None = None,
    segment: str | None = None,
    sector: str | None = None,
) -> Sequence[Instrument]:
    stmt = select(Instrument).order_by(Instrument.symbol)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            or_(
                Instrument.symbol.ilike(pattern),
                Instrument.name.ilike(pattern),
                Instrument.isin.ilike(pattern),
            )
        )
    if exchange:
        stmt = stmt.where(Instrument.exchange == exchange)
    if segment:
        stmt = stmt.where(Instrument.segment == segment)
    if sector:
        stmt = stmt.where(Instrument.sector == sector)
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_instrument_by_id(db: AsyncSession, instrument_id: uuid.UUID) -> Instrument | None:
    stmt = select(Instrument).where(Instrument.id == instrument_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_instrument_by_symbol(db: AsyncSession, symbol: str) -> Instrument | None:
    stmt = select(Instrument).where(Instrument.symbol == symbol.upper())
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def update_instrument(db: AsyncSession, db_obj: Instrument, obj_in: InstrumentUpdate) -> Instrument:
    update_data = obj_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_obj, field, value)
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj
