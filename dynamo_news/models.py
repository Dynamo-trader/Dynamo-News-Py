import pytz
from datetime import datetime
from enum import Enum
from typing import Union, Optional

from pydantic import BaseModel, field_validator
from pydantic import Field

from dynamo_news.constant import TZ
from dynamo_news.funcs import remove_special_chars


class News(BaseModel):
    event_id: Union[int, str]
    event_time: datetime
    all_day: bool
    currency: str
    country: Optional[str] = Field(default="")
    rating: int = Field(..., ge=0, le=3)
    event_name: str
    actual: Union[str, int, float]
    forecast: Union[str, int, float]
    previous: Union[str, int, float]
    verdict: int
    soloUrl: str
    ebase_id: int
    hasGraph: bool

    @field_validator("event_time")
    def astimezone(cls, v):
        if v.tzinfo is None:
            return v.replace(tzinfo=pytz.utc).astimezone(TZ)
        return v

    @field_validator("actual", "forecast", "previous")
    def to_float(cls, v) -> Union[float, int]:
        if isinstance(v, str):
            if len(v) == 0:
                return 0
            return float(remove_special_chars(v))
        return v


class NewsSource(str, Enum):
    INVESTING = "inews"
    FOREX_FACTORY = "ffnews"


class ForexFactory(BaseModel):
    event_name: str
    name: str
    title: str
    label: str
    currency: str
    country: str
    pips: list[float]
    sl_pip: float = Field(default=10, gt=0)
    cid: list[int]
    bull_condition: str
    eq_condition: str
    text: str
    main_pairs: list[str]
    inverse_pairs: list[str]
    delay_long: float = Field(default=0, ge=0)
    delay_short: float = Field(default=0, ge=0)
