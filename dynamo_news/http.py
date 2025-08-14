import asyncio
from typing import Union, Any
from urllib.parse import urlencode

import httpx
import cloudscraper

http = httpx.AsyncClient()
scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "mobile": True}
)


async def fetch_url_async(u: str, return_json: bool = True):
    loop = asyncio.get_event_loop()
    r = await loop.run_in_executor(None, scraper.get, u)
    return r.json() if return_json else r.text


async def get_http(
    url: str, params: dict[str, str] = None, api_key: str = None
) -> Union[dict, list]:
    if params:
        params = {k: v for k, v in params.items() if v is not None}
        encoded_params = urlencode(params)
        url = f"{url}?{encoded_params}"
    # try zstd or gzip compression
    headers = {"Accept-Encoding": "gzip"}
    if api_key:
        headers["X-API-KEY"] = api_key
    response = await http.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


async def post_http(
    url: str,
    params: dict[str, str] = None,
    data: Union[dict, str] = None,
    json: Union[dict, str] = None,
    api_key: str = None,
) -> Union[Any]:
    if params:
        params = {k: v for k, v in params.items() if v is not None}
        encoded_params = urlencode(params)
        url = f"{url}?{encoded_params}"
    headers = {"Content-Type": "application/json"}

    if api_key:
        headers["X-API-KEY"] = api_key
    response = await http.post(url, data=data, json=json, headers=headers)
    response.raise_for_status()
    try:
        return response.json()
    except Exception:  # noqa
        return None
