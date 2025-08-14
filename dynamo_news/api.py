import logging
import pytz

from datetime import datetime
from typing import Union

from dynamo_news.http import post_http, get_http
from dynamo_news.models import NewsSource, News


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

    url = f"https://dynamoapi.dynamo-link.com/{source.value}"
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
    url = "https://dynamoapi.dynamo-link.com/get-news"
    response = await get_http(
        url,
        params={
            "news_id": news_id,
            "source": source.value,
        },
        api_key=api_key,
    )
    return News(**response)
