import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Optional, Union

import pytz
from dateutil.relativedelta import relativedelta
from pymongo import UpdateOne
from pymongo.asynchronous.collection import AsyncCollection

from dynamo_news.constant import TZ
from dynamo_news.funcs import replace_x_x
from dynamo_news.http import fetch_url_async, http, scraper
from dynamo_news.models import ForexFactory, News

lock = asyncio.Lock()


async def scrap_with_lock(db_news: AsyncCollection, db_timeline: AsyncCollection):
    if lock.locked():
        while lock.locked():
            await asyncio.sleep(5)
        return

    async with lock:
        await update_forexfactory_calendar(
            db_news=db_news,
            db_timeline=db_timeline,
            return_early=True,
            start_date=datetime.now(TZ) - timedelta(days=1),
            end_date=datetime.now(TZ) + timedelta(days=1),
        )


async def scrap_forex_factory_event_timeline(event_id: int) -> list[dict]:
    url = f"https://www.forexfactory.com/calendar/graph/{event_id}?limit=200&site_id=1"
    try:
        response = await fetch_url_async(url)
        return response["data"]["events"]
    except Exception as e:
        logging.exception("Error in get_event_data", exc_info=e)
        return []


async def get_forex_event(event_id: int) -> dict:
    url = f"https://faireconomy.media/calendar/{event_id}.json"
    response = await http.get(url)

    if response.status_code != 200:
        return {}
    return response.json()


async def get_forexfactory_trade_event(
    event_name: str, currency: str, db_trade_event: AsyncCollection
) -> Optional[ForexFactory]:
    r = await db_trade_event.find_one({"event_name": event_name, "currency": currency})
    if r:
        return ForexFactory(**r)


async def update_forexfactory_calendar(
    db_news: AsyncCollection,
    db_timeline: AsyncCollection,
    return_early: bool = False,
    previous_news: list[dict] = None,
    start_date: datetime = None,
    end_date: datetime = None,
) -> Union[list[News]]:
    logging.info("Updating Forex Factory Calendar...")

    current_date = datetime.now()
    start_of_current_month = current_date.replace(day=1)

    if not start_date or not end_date:
        start_date = (current_date.replace(day=1) - timedelta(days=1)).replace(day=1)
        end_date = (start_of_current_month + relativedelta(months=2)).replace(
            day=1
        ) - timedelta(days=1)

    body = {
        "default_view": "today",
        "impacts": [3, 2, 1],
        "event_types": [1, 2, 3, 4, 5, 7, 8, 9, 10, 11],
        "currencies": [1, 2, 3, 4, 5, 6, 7, 8, 9],
        "begin_date": start_date.strftime("%B %d, %Y"),
        "end_date": end_date.strftime("%B %d, %Y"),
    }

    req = scraper.post(
        "https://www.forexfactory.com/calendar/apply-settings/1?navigation=0",
        data=json.dumps(body),
    )
    days = req.json()["days"]

    newses = []
    for day in days:
        for event in day["events"]:
            event_name = re.sub(r"\b\w/\w\b", replace_x_x, event["name"])
            utc_timestamp = event["dateline"]
            event_time = datetime.fromtimestamp(utc_timestamp, pytz.UTC)
            all_day = True if event["timeLabel"] == "All Day" else False
            rating = (
                3
                if "High" in event["impactTitle"]
                else 2
                if "Medium" in event["impactTitle"]
                else 1
            )

            newses.append(
                {
                    "event_id": event["id"],
                    "event_time": event_time,
                    "utc_timestamp": utc_timestamp,
                    "all_day": all_day,
                    "country": event["country"],
                    "currency": event["currency"],
                    "rating": rating,
                    "event_name": event_name,
                    "actual": event["actual"],
                    "forecast": event["forecast"],
                    "previous": event["previous"],
                    "verdict": event["actualBetterWorse"],
                    "soloUrl": event["soloUrl"],
                    "ebase_id": event["ebaseId"],
                    "hasGraph": event["hasGraph"],
                }
            )

    bulk_write = []

    # sort news by event_time
    newses = sorted(newses, key=lambda x: x["event_time"])
    logging.info(f"Found {len(newses)} news events...")

    # Iterate through each new item in the list of news
    for new in newses:
        filter_criteria = {"event_id": new["event_id"]}
        update_operation = {"$set": new}
        update_one_operation = UpdateOne(filter_criteria, update_operation, upsert=True)
        bulk_write.append(update_one_operation)

    await db_news.bulk_write(bulk_write)
    if previous_news:
        newses = previous_news + newses

    r = []

    logging.info(f"Getting timeline for {len(newses)} news events...")

    done_timeline = []
    for new in reversed(newses):
        try:
            if not return_early and new["ebase_id"] not in done_timeline:
                done_timeline.append(new["ebase_id"])
                if news_line := await scrap_forex_factory_event_timeline(
                    new["event_id"]
                ):
                    await db_timeline.update_one(
                        {
                            "event_name": new["event_name"],
                            "currency": new["currency"],
                            "ebase_id": new["ebase_id"],
                        },
                        {
                            "$set": {
                                "event_id": new["event_id"],
                                "news_line": news_line,
                            }
                        },
                        upsert=True,
                    )
                    await asyncio.sleep(0.5)

            n = News(**new)
            r.append(n)
        except Exception as e:
            if (
                "actual" not in str(e)
                and "forecast" not in str(e)
                and "previous" not in str(e)
            ):
                logging.exception("Error in getting news timeline", exc_info=e)

    return r
