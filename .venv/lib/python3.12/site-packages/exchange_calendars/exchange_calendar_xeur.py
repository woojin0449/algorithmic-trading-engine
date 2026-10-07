from datetime import time
from zoneinfo import ZoneInfo

from pandas.tseries.holiday import EasterMonday, GoodFriday

from .common_holidays import (
    boxing_day,
    christmas,
    christmas_eve,
    european_labour_day,
    new_years_day,
    new_years_eve,
)
from .exchange_calendar import ExchangeCalendar, HolidayCalendar

# Regular Holidays
# ----------------
NewYearsDay = new_years_day()

EuropeanLabourDay = european_labour_day()

ChristmasEve = christmas_eve()

Christmas = christmas()

BoxingDay = boxing_day()

NewYearsEve = new_years_eve()


class XEURExchangeCalendar(ExchangeCalendar):
    """
    Exchange calendar for Eurex (XEUR).
    https://www.eurex.com/ex-en/trade/trading-calendar/holiday-regulations

    Open Time: 8:00 AM, CET
    Close Time: 22:00 PM, CET

    Regularly-Observed Holidays:
    - New Years Day
    - Good Friday
    - Easter Monday
    - Labour Day
    - Christmas Eve
    - Christmas Day
    - Boxing Day
    - New Year's Eve
    """

    name = "XEUR"

    tz = ZoneInfo("Europe/Berlin")

    open_times = ((None, time(8)),)

    close_times = ((None, time(22, 0)),)

    @property
    def regular_holidays(self):
        return HolidayCalendar(
            [
                NewYearsDay,
                GoodFriday,
                EasterMonday,
                EuropeanLabourDay,
                ChristmasEve,
                Christmas,
                BoxingDay,
                NewYearsEve,
            ]
        )
