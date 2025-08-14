import asyncio
import logging
import os
from typing import Optional

import discord
import pytz
import time
from datetime import datetime, timedelta

from aiogram import Bot
from discord import Client
from pymongo.asynchronous.collection import AsyncCollection

from dynamo_news.api import get_news, get_one_news
from dynamo_news.constant import LOGO_BLACK, cid, TZ, wait_for_result, alternative_labels, \
    alternative_conditional_labels, no_dc_trade_channel, no_tg_trade_channel, CURRENCY_EMOJI
from dynamo_news.db import get_forexfactory_trade_events
from dynamo_news.funcs import remove_special_chars
from dynamo_news.models import News, ForexFactory, NewsSource
from dynamo_news.plot import get_plot
from dynamo_news.schedulers import schedule_ids, schedule
from dynamo_news.scrapper import scrap_forex_factory_event_timeline, get_forex_event, get_forexfactory_trade_event, \
    scrap_with_lock
from dynamo_news.sender import edit_or_send


async def get_updated_forex_factory_event_timeline(
        news: News,
        last_date: int,
        updated_news: dict,
):
    new_date_datas: list[dict] = await scrap_forex_factory_event_timeline(news.event_id)
    if new_date_datas[-1]["dateline"] < last_date:
        #         {
        #              'actual': 303,
        #              'actual_formatted': '303K',
        #              'date': 'Apr 2024',
        #              'dateline': 1712320200,
        #              'forecast': 212,
        #              'forecast_formatted': '212K',
        #              'id': 135981,
        #              'is_active': False,
        #              'is_most_recent': False,
        #              'revision': 315,
        #              'revision_formatted': '315K'
        #         }
        new_date_datas[-1] = {
            "actual": float(remove_special_chars(updated_news["actual"])),
            "actual_formatted": updated_news["actual"],
            "date": datetime.fromtimestamp(updated_news["dateline"], tz=pytz.UTC).strftime("%b %Y"),
            "dateline": updated_news["dateline"],
            "forecast": float(remove_special_chars(updated_news["forecast"])),
            "forecast_formatted": updated_news["forecast"],
            "id": news.event_id,
            "is_active": True,
            "is_most_recent": True,
            "revision": float(remove_special_chars(updated_news["previous"])) if updated_news["previous"] else None,
            "revision_formatted": updated_news["previous"] if updated_news["previous"] else None,
        }

    return new_date_datas


async def get_updated_forex_factory_event(
        event_id: int,
        last_date: int,
        send_previous: bool = False
):
    start_time = time.perf_counter()

    for idx in range(1000):
        logging.info(f"Trying for {idx}th time...")
        try:
            new_date_data = await get_forex_event(event_id=event_id)
        except Exception as e:
            logging.exception(e)
            await asyncio.sleep(5)
            continue

        new_date: int = new_date_data["dateline"]
        actual: str = new_date_data.get("actual", "")
        if send_previous:
            break
        elif last_date < new_date and actual != "":
            break
        await asyncio.sleep(2)
    else:
        return {}

    end_time = time.perf_counter()

    return {
        "new_date_data": new_date_data,
        "start_time": start_time,
        "end_time": end_time,
    }


async def send_forex_factory_trades(
    news_condition: ForexFactory,
    event_id: int,
    last_date: int,
    db_timeline: AsyncCollection,
    db_trade_event: AsyncCollection,
    drb: Client,
    trb: Bot,
    send_previous: bool = False,
):
    news_condition = await get_forexfactory_trade_event(
        event_name=news_condition.event_name,
        currency=news_condition.currency,
        db_trade_event=db_trade_event
    )

    if not news_condition:
        logging.info(f"News {news_condition.event_name} not found.")
        return

    news: News = await get_one_news(
        news_id=str(event_id), source=NewsSource.FOREX_FACTORY
    )

    all_new_date_data = await get_updated_forex_factory_event(
        event_id=event_id,
        last_date=last_date,
        send_previous=send_previous
    )

    new_date_data: dict = all_new_date_data.get("new_date_data", None)
    logging.info(new_date_data)
    if not new_date_data:
        logging.warning(f"News {news.event_name} did not updated the actual value.")
        return

    actual: str = new_date_data["actual"]
    actual_formatted = new_date_data["actual"]
    previous_formatted = new_date_data["previous"]
    forecast_formatted = new_date_data["forecast"]

    start_time = all_new_date_data["start_time"]
    end_time = all_new_date_data["end_time"]

    if not actual or not new_date_data:
        logging.warning(f"News {news.event_name} did not updated the actual ({actual}) value.")
        return

    actual: float = float(remove_special_chars(actual))

    if news.forecast == actual:
        sign = "="
        if news_condition.eq_condition == "long":
            direction = "Long"
        elif news_condition.eq_condition == "short":
            direction = "Short"
        else:
            logging.info(
                f"News {news.event_name} actual value is equal to forecast. No trade."
            )
            direction = None

            text = (
                f"{news.currency} {news.event_name} {actual} v {news.forecast}. "
                f" No trade triggered as per the parameters set to no trade when result is as expected."
            )

            try:
                channel = drb.get_channel(no_dc_trade_channel)
                await channel.send(text)
                await trb.send_message(no_tg_trade_channel, text)
            except Exception as e:
                logging.exception(e)

    else:
        logging.info(
            f"news.forecast > actual={news.forecast > actual}\n"
            f"{news.forecast=}, {actual=}\n"
            f"news_condition.bull_condition={news_condition.bull_condition}\n"
        )
        if news_condition.bull_condition == "above":
            if actual > news.forecast:
                direction = "Long"
                sign = ">"
            else:
                direction = "Short"
                sign = "<"
        else:
            if actual < news.forecast:
                direction = "Long"
                sign = ">"
            else:
                direction = "Short"
                sign = "<"

    logging.info(news)
    logging.info(news_condition)

    if direction:
        trade_info = {
            "direction": direction,
            "sign": sign,
            "is_long": direction == "Long",
            "actual": actual,
            "news": news.model_dump(),
            "condition": news_condition.model_dump(),
        }
        logging.info(trade_info)

        wait_for_result.setdefault(news_condition.currency, {})
        wait_for_result[news_condition.currency][news_condition.label] = {
            "actual": actual,
            "forecast": news.forecast,
        }

        today = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
        newses_today = await get_news(
            start_date=today,
            end_date=today + timedelta(days=1),
            source=NewsSource.FOREX_FACTORY,
        )

        alternative_label = alternative_labels.get(news_condition.label, None)
        alternative_conditional_label: list[dict] = alternative_conditional_labels.get(
            news_condition.label, None
        )

        if alternative_label is not None:
            for n in newses_today:
                if n.event_name == alternative_label["label"]:
                    if alternative_label["condition"] == "stop":
                        return

                    for _ in range(1000):
                        exists: Optional[dict] = wait_for_result.get(
                            news_condition.currency, {}
                        ).get(alternative_label["label"], None)
                        if exists is not None:
                            alt_actual: float = exists.get("actual")
                            if (alt_actual >= 0 and actual >= 0) or (
                                    alt_actual < 0 and actual < 0
                            ):
                                break

                            text = (
                                f"{news.currency} {news.event_name} {actual} v {news.forecast}. "
                                f" No trade triggered as per the parameters set to no trade when result is as expected."
                            )

                            logging.info(text)

                            try:
                                channel = drb.get_channel(no_dc_trade_channel)
                                await channel.send(text)
                            except Exception as e:
                                logging.exception(e)

                            try:
                                await trb.send_message(no_tg_trade_channel, text)
                            except Exception as e:
                                logging.exception(e)

                            return
                        await asyncio.sleep(2)
                    else:
                        text = (
                            f"{news.currency} {news.event_name} {actual} v {news.forecast}. "
                            f"No trade triggered because failed to match the alternative condition"
                        )

                        logging.info(text)

                        try:
                            channel = drb.get_channel(no_dc_trade_channel)
                            await channel.send(text)
                        except Exception as e:
                            logging.exception(e)

                        try:
                            await trb.send_message(no_tg_trade_channel, text)
                        except Exception as e:
                            logging.exception(e)

                        return
                    break

        elif alternative_conditional_label is not None:
            alt_labels: set[str] = {alt["alt"]["label"] for alt in alternative_conditional_label}

            for _ in range(1000):
                if any(
                    [
                        wait_for_result.get(news_condition.currency, {}).get(alt_label, None)
                        for alt_label in alt_labels
                    ]
                ):
                    break
                await asyncio.sleep(2)
            else:
                text = (
                    f"{news.currency} {news.event_name} {actual} v {news.forecast}. "
                    f" No trade triggered because failed to match the alternative condition {' '.join(alt_labels)}"
                )

                logging.info(text)

                try:
                    channel = drb.get_channel(no_dc_trade_channel)
                    await channel.send(text)
                except Exception as e:
                    logging.exception(e)

                try:
                    await trb.send_message(no_tg_trade_channel, text)
                except Exception as e:
                    logging.exception(e)
                return

            for alt in alternative_conditional_label:
                condition = alt["condition"]
                alt_label = alt["alt"]["label"]
                alt_condition = alt["alt"]["condition"]

                exists: Optional[dict] = wait_for_result.get(
                    news_condition.currency, {}
                ).get(alt_label, None)

                if exists is None:
                    continue

                if condition == "above" and actual < news.forecast:
                    continue
                elif condition == "below" and actual > news.forecast:
                    continue

                alt_actual: float = exists.get("actual")
                alt_forecast: float = exists.get("forecast")
                if alt_condition == "above" and alt_actual < alt_forecast:
                    continue
                elif alt_condition == "below" and alt_actual > alt_forecast:
                    continue
                break
            else:
                text = (
                    f"{news.currency} {news.event_name} {actual} v {news.forecast}. "
                    f" No trade triggered as per the parameters set to no trade when result is as expected."
                )

                logging.info(text)

                try:
                    channel = drb.get_channel(no_dc_trade_channel)
                    await channel.send(text)
                except Exception as e:
                    logging.exception(e)

                try:
                    await trb.send_message(no_tg_trade_channel, text)
                except Exception as e:
                    logging.exception(e)
                return

        # await asyncio.sleep(5)
        # for x in trade_link_sent:
        #     try:
        #         await x.delete()
        #     except Exception as e:
        #         logging.exception(e)

    new_date_datas = await get_updated_forex_factory_event_timeline(
        news=news,
        last_date=last_date,
        updated_news=new_date_data,
    )

    if new_date_datas:
        await db_timeline.update_one(
            {
                "event_name": news.event_name,
                "currency": news.currency,
                "ebase_id": news.ebase_id,
            },
            {
                "$set": {
                    "event_id": news.event_id,
                    "news_line": new_date_datas,
                }
            },
            upsert=True,
        )

    plot_data = []
    for event_data in new_date_datas:
        date = datetime.fromtimestamp(
            event_data["dateline"], tz=pytz.UTC
        ).astimezone(TZ)
        plot_data.append(
            [
                date,
                event_data.get("actual", 0),
                event_data.get("forecast", 0),
                event_data.get("previous", 0),
            ]
        )

    plot_file = get_plot(plot_data, news_condition)

    event_link = (
        f"https://www.forexfactory.com/calendar"
        f"?day={news.event_time:%b%d.%Y}#detail={news.event_id}"
    )
    flag = CURRENCY_EMOJI.get(news.currency, "")
    flag = flag if not flag else f" {flag}"

    main_pairs = ", ".join(news_condition.main_pairs)
    inverse_pairs = ", ".join(news_condition.inverse_pairs)

    description = (
        f"{news.country}{flag} {news.event_name}\n"
        f"Actual: {actual_formatted}\n"
        f"Forecast: {forecast_formatted}\n"
        f"Previous: {previous_formatted}\n"
        f"Triggered main pairs: {main_pairs} ({'Long' if direction == 'Long' else 'Short'})\n"
        f"Triggered inverse pairs: {inverse_pairs} ({'Short' if direction == 'Long' else 'Long'})\n"
        f"Took: {end_time - start_time:.2f} Seconds\n"
    )

    embed = discord.Embed(
        title=f"{news.currency} {news.event_name}",
        description=description,
        url=event_link,
    )

    embed.set_footer(
        icon_url=LOGO_BLACK,
        text="Dynamo Trader",
    )

    try:
        file = discord.File(fp=plot_file, filename=plot_file)
        embed.set_image(url=f"attachment://{plot_file}")

        for x in cid:
            channel = await edit_or_send(
                drb=drb,
                channel_id=x,
                embed=embed,
                file=file,
                send_for=news_condition.label.lower(),
            )
            logging.info(f"{news.event_name} sent to ({channel.id})")
    except Exception as e:
        logging.exception("Error uploading to TG: ", exc_info=e)

    os.remove(plot_file)


async def fifteen_minutes_announcement(
    db_news: AsyncCollection,
    db_timeline: AsyncCollection,
    db_trade_event: AsyncCollection,
    drb: Client,
    news_condition: ForexFactory,
    event_id: int,
    lt: bool = False
):
    news_condition = await get_forexfactory_trade_event(
        event_name=news_condition.event_name,
        currency=news_condition.currency,
        db_trade_event=db_trade_event
    )

    if not news_condition:
        logging.info(f"News {news_condition.event_name} not found.")
        return

    await scrap_with_lock(db_news=db_news, db_timeline=db_timeline)
    news: News = await get_one_news(
        news_id=str(event_id),
        source=NewsSource.FOREX_FACTORY
    )

    logging.info("Sending 15 minutes warning...")

    text = f"""{news.event_name} for {news.event_time:%d-%m-%Y %I:%M %p} LIVE in{' less than' if lt else ''} 15 minutes 📣
➡️ Forecast {news.forecast}  Previous {news.previous}
actual < {news.forecast} is {'Long' if news_condition.bull_condition == 'below' else 'Short'} 🚀
actual > {news.forecast} is {'Short' if news_condition.bull_condition == 'below' else 'Long'} 🐻
actual = {news.forecast} is {news_condition.eq_condition.title()}

Main Pairs: {', '.join(news_condition.main_pairs)}
Inverse Pairs: {', '.join(news_condition.inverse_pairs)}
    """  # noqa

    title = f"{news.event_name} - {news.currency}{' - ' + news.country if news.country != news.currency else ''}"
    to_delete = []
    for xcid in cid:
        embed = discord.Embed(
            title=title,
            description=text,
            color=0x00FF00,
            timestamp=news.event_time,
        )
        embed.set_footer(text="Dynamo Trader", icon_url=LOGO_BLACK)
        channel = drb.get_channel(xcid)
        sent = await channel.send(embed=embed)
        to_delete.append(sent)

    seconds_left = (news.event_time - datetime.now(TZ)).seconds + 120
    if seconds_left > 0:
        await asyncio.sleep(seconds_left)

    for message in to_delete:
        try:
            await message.delete()
        except Exception as e:
            logging.exception(e)


async def forex_factory_trade_events(
    db_news: AsyncCollection,
    db_timeline: AsyncCollection,
    db_trade_event: AsyncCollection,
    drb: Client,
    trb: Bot,
    send_previous: bool = False
):
    logging.info("Starting forex_factory_trade_events...")
    today = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    newses_today = await get_news(
        start_date=today,
        end_date=today + timedelta(days=1),
        source=NewsSource.FOREX_FACTORY,
    )
    now = datetime.now(TZ)
    trade_newses = []

    trade_events = await get_forexfactory_trade_events(db_trade_event=db_trade_event)
    logging.info(f"Trade events: {len(trade_events)}")
    for news_today in newses_today:
        for trade_news in trade_events:
            if news_today.event_name.lower() != trade_news.event_name.lower():
                continue
            if news_today.currency != trade_news.currency:
                continue
            if (
                    trade_news.currency != trade_news.country
                    and trade_news.country.lower() not in news_today.event_name.lower()
            ):
                continue
            if news_today.event_time < now:
                logging.info(f"Event {news_today.event_name} is already passed.")
                if send_previous:
                    logging.info(f"Sending previous trades for {news_today.event_name}")
                    last_date = (
                        await scrap_forex_factory_event_timeline(news_today.event_id)
                    )[-1]["dateline"]
                    await send_forex_factory_trades(
                        news_condition=trade_news,
                        event_id=news_today.event_id,
                        last_date=last_date,
                        send_previous=send_previous,
                        drb=drb,
                        trb=trb,
                        db_trade_event=db_trade_event,
                        db_timeline=db_timeline
                    )
                continue
            trade_newses.append({"news_conditions": trade_news, "news": news_today})
            break

    # # Step 1: Count occurrences of each event_time
    # event_time_counts = Counter(
    #     trade_news["news"].event_time for trade_news in trade_newses
    # )
    #
    # # Step 2: Filter out news with duplicate event_times
    # trade_newses[:] = [
    #     trade_news
    #     for trade_news in trade_newses
    #     if event_time_counts[trade_news["news"].event_time] == 1
    #     or trade_news["news"].rating != 3
    # ]

    logging.info(f"Trade news events found: {len(trade_newses)}")

    for c_trade_news in trade_newses:
        trade_news = c_trade_news["news"]

        logging.info(
            f"News to trade: {trade_news.event_name} at {trade_news.event_time:%d-%m-%Y %I:%M %p}"
        )
        last_date = (await scrap_forex_factory_event_timeline(trade_news.event_id))[-1][
            "dateline"
        ]

        id_1 = f'fifteen_minutes_announcement("{trade_news.event_name}")'
        id_2 = f'send_forex_factory_trades("{trade_news.event_name}")'

        if not schedule.get_job(id_1):
            if (trade_news.event_time - timedelta(minutes=15)) < now:
                asyncio.create_task(  # noqa
                    fifteen_minutes_announcement(
                        news_condition=c_trade_news["news_conditions"],
                        event_id=c_trade_news["news"].event_id,
                        lt=True,
                        db_news=db_news,
                        db_timeline=db_timeline,
                        drb=drb,
                        db_trade_event=db_trade_event
                    )
                )
            else:
                schedule_ids.append(
                    schedule.add_job(
                        fifteen_minutes_announcement,
                        kwargs={
                            "event_id": c_trade_news["news"].event_id,
                            "news_condition": c_trade_news["news_conditions"],
                            "db_news": db_news,
                            "db_timeline": db_timeline,
                            "drb": drb,
                        },
                        trigger="date",
                        run_date=trade_news.event_time - timedelta(minutes=15),
                        name=id_1,
                        id=id_1,
                    )
                )
        else:
            logging.info(f"Job {id_1} already exists")

        if not schedule.get_job(id_2):
            schedule_ids.append(
                schedule.add_job(
                    send_forex_factory_trades,
                    kwargs={
                        "news_condition": c_trade_news["news_conditions"],
                        "event_id": c_trade_news["news"].event_id,
                        "last_date": last_date,
                    },
                    trigger="date",
                    run_date=trade_news.event_time,
                    name=id_2,
                    id=id_2,
                )
            )
        else:
            logging.info(f"Job {id_2} already exists")

    logging.info(f"Trade news events scheduled: {len(trade_newses)}")