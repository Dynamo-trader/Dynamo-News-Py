from typing import Optional

from pymongo.asynchronous.collection import AsyncCollection

from dynamo_news.models import ForexFactory


async def get_forexfactory_trade_events(
    db_trade_event: AsyncCollection,
) -> list[ForexFactory]:
    return [ForexFactory(**x) async for x in db_trade_event.find().sort("currency")]


async def get_forexfactory_trade_event(
    event_name: str, currency: str, db_trade_event: AsyncCollection
) -> Optional[ForexFactory]:
    r = await db_trade_event.find_one({"event_name": event_name, "currency": currency})
    if r:
        return ForexFactory(**r)
