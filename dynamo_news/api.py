import logging
import pytz

from datetime import datetime
from typing import Union

from dynamo_news.http import post_http, get_http
from dynamo_news.math import calculate_pip_value
from dynamo_news.models import NewsSource, News
from dynamo_news.pair_info import pair_infos

base_url = "https://dynamoapi.dynamo-link.com"


async def get_news(
    api_key: str,
    start_date: datetime,
    end_date: datetime,
    source: NewsSource,
    min_rating: int = None,
    whitelisted_currencies: list[str] = None,
    blacklist_currencies: list[str] = None,
):
    # convert dates to utc timezone and then to string
    if not start_date.tzinfo or not end_date.tzinfo:
        raise ValueError("Dates must have timezone information")

    url = f"{base_url}/{source.value}"
    response: list[dict] = await post_http(
        url,
        api_key=api_key,
        json={
            "start_date": start_date.astimezone(pytz.UTC).isoformat(),
            "end_date": end_date.astimezone(pytz.UTC).isoformat(),
            "min_rating": min_rating,
            "whitelisted_currencies": whitelisted_currencies,
            "blacklist_currencies": blacklist_currencies,
        },
    )

    newses = []
    for news in response:
        try:
            newses.append(News(**news))
        except BaseException:  # NOQA
            logging.error(f"Error parsing {source} news: {news}")
    return newses


async def get_one_news(
    api_key: str, news_id: str, source: NewsSource
) -> Union[News, None]:
    url = f"{base_url}/get-news"
    response = await get_http(
        url,
        params={
            "news_id": news_id,
            "source": source.value,
        },
        api_key=api_key,
    )
    return News(**response)


async def pip_diff(
    symbols: list[str], prices: list[float], pip_steps: list[int], api_key: str
) -> dict:
    diff = {}
    not_found = {}

    for symbol, price in zip(symbols, prices):
        pair_info = pair_infos.get(symbol)
        if not pair_info:
            not_found[symbol] = price
        new_price: list[float] = calculate_pip_value(
            price=price, pip_steps=pip_steps, decimal_places=pair_info["digits"]
        )

        # match index of the pips to determine if it is + or -
        prices_to = []
        prices_to_negative = []

        for np in new_price:
            if pip_steps[new_price.index(np)] >= 0:
                prices_to.append(np)
            else:
                prices_to_negative.append(np)

        diff[symbol] = {
            "price_from": price,
            "prices_to": prices_to,
            "prices_to_negative": prices_to_negative,
        }

    if not_found:
        url = f"{base_url}/pip-diff"
        data = {
            "symbols": [x for x in not_found],
            "prices": [not_found[x] for x in not_found],
            "pip_steps": pip_steps,
        }
        response = await post_http(
            url,
            api_key=api_key,
            json=data,
        )

        diff.update(response)
    return diff
