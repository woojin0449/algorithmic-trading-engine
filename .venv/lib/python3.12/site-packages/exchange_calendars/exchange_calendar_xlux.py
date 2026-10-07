from datetime import time
from zoneinfo import ZoneInfo

from pandas.tseries.holiday import EasterMonday, GoodFriday

from .exchange_calendar import WEEKDAYS, HolidayCalendar, ExchangeCalendar

from .common_holidays import (
    new_years_eve,
    new_years_day,
    european_labour_day,
    christmas,
    christmas_eve,
    boxing_day,
)

NewYearsEve = new_years_eve(days_of_week=WEEKDAYS)
NewYearsDay = new_years_day()
LabourDay = european_labour_day()
Christmas = christmas()
ChristmasEve = christmas_eve(days_of_week=WEEKDAYS)
BoxingDay = boxing_day()


class XLUXExchangeCalendar(ExchangeCalendar):
    """
    Exchange calendar for the Luxembourg Stock Exchange (XLUX).

    Open Time: 9:00 AM, CET
    Close Time: 5:40 PM, CET

    Regularly-Observed Holidays:
    - New Years Day
    - Good Friday
    - Easter Monday
    - Labour Day
    - Christmas Day
    - Boxing Day

    Early Closes:
    - Christmas Eve
    - New Year's Eve
    """

    # Source: https://www.luxse.com/trading/opening-hours-and-closing-days

    name = "XLUX"  # Luxembourg Stock Exchange
    tz = ZoneInfo("Europe/Luxembourg")
    open_times = ((None, time(9, 0)),)
    close_times = ((None, time(17, 40)),)
    regular_early_close = time(14, 5)

    @property
    def regular_holidays(self):
        return HolidayCalendar(
            [
                NewYearsDay,
                GoodFriday,
                EasterMonday,
                LabourDay,
                Christmas,
                BoxingDay,
            ]
        )

    @property
    def special_closes(self):
        return [
            (
                self.regular_early_close,
                HolidayCalendar(
                    [
                        ChristmasEve,
                        NewYearsEve,
                    ]
                ),
            )
        ]
