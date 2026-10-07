from datetime import (
    time,
    datetime,
    timedelta,
)
from itertools import chain
from zoneinfo import ZoneInfo
import pandas as pd
from pandas.tseries.holiday import (
    Holiday,
    sunday_to_monday,
)
from .common_holidays import (
    new_years_day,
    orthodox_good_friday,
    orthodox_easter_monday,
)
from .exchange_calendar import HolidayCalendar, ExchangeCalendar


def sunday_to_tuesday(dt: datetime) -> datetime:
    """
    If holiday falls on Sunday, use Tuesday instead.
    """
    if dt.weekday() == 6:
        return dt + timedelta(2)
    return dt


NewYearsDay = new_years_day(observance=sunday_to_tuesday)
NewYearsDay2 = Holiday("New Year's Day", month=1, day=2, observance=sunday_to_monday)
OrthodoxChristmas = Holiday("Christmas Holiday", month=1, day=7)
StatehoodDay = Holiday(
    "Statehood Day of Serbia", month=2, day=15, observance=sunday_to_tuesday
)
StatehoodDay2 = Holiday(
    "Statehood Day of Serbia Holiday", month=2, day=16, observance=sunday_to_monday
)
OrthodoxGoodFriday = orthodox_good_friday()
OrthodoxEasterMonday = orthodox_easter_monday()
LabourDay = Holiday("Labour Day", month=5, day=1, observance=sunday_to_tuesday)
LabourDay2 = Holiday("Labour Day Holiday", month=5, day=2, observance=sunday_to_monday)
ArmisticeDay = Holiday("Armistice Day", month=11, day=11, observance=sunday_to_monday)


class XBELExchangeCalendar(ExchangeCalendar):
    """
    Calendar for the Belgrade Stock Exchange (Serbia).
    https://www.belex.rs/eng/trzista_i_hartije/kalendar

    Open Time: 9:30 AM
    Close Time: 2:00 PM

    Regularly-Observed Holidays:
      - New Year's Day (Jan 1)
      - Orthodox Christmas (Jan 7)
      - Statehood Day (Feb 15-16)
      - Orthodox Good Friday
      - Orthodox Easter Monday
      - Labour Day (May 1-2)
      - Armistice Day (Nov 11)
    """

    name = "XBEL"
    tz = ZoneInfo("Europe/Belgrade")
    open_times = ((None, time(9, 30)),)
    close_times = ((None, time(14, 00)),)

    @property
    def regular_holidays(self):
        return HolidayCalendar(
            [
                NewYearsDay,
                NewYearsDay2,
                OrthodoxChristmas,
                StatehoodDay,
                StatehoodDay2,
                OrthodoxGoodFriday,
                OrthodoxEasterMonday,
                LabourDay,
                LabourDay2,
                ArmisticeDay,
            ]
        )

    @property
    def adhoc_holidays(self):
        # Latest calendar: https://www.belex.rs/eng/trzista_i_hartije/kalendar
        # Historical calendars: https://www.belex.rs/eng/search_c/calendar
        # Exchange calendar 2025: https://www.belex.rs/data/2024/12/00140175_E.pdf
        # Exchange calendar 2024: https://www.belex.rs/data/2023/12/00135552_E.pdf
        # Exchange calendar 2023: https://www.belex.rs/data/2022/11/00130092_E.pdf
        # Exchange calendar 2022: https://www.belex.rs/data/2021/11/00124168_E.pdf
        # Exchange calendar 2021: https://www.belex.rs/data/2020/10/00117713_E.pdf
        misc_adhoc_holidays = [
            pd.Timestamp(
                "2025-12-31"
            ),  # Trading system maintenance, statistics and data migration
            pd.Timestamp(
                "2025-11-10"
            ),  # Relocation of CSDs servers and network equipment to a new address
            pd.Timestamp("2025-01-06"),  # Security improvement of the trading platform
            pd.Timestamp("2025-01-03"),  # Security improvement of the trading platform
            pd.Timestamp(
                "2024-12-31"
            ),  # Trading system maintenance, statistics and data migration
            pd.Timestamp(
                "2024-01-08"
            ),  # Day off for the second day of Orthodox Christmas
            pd.Timestamp(
                "2023-12-29"
            ),  # Trading system maintenance, statistics and data migration
            pd.Timestamp("2023-01-06"),  # Market closed
            pd.Timestamp("2023-01-05"),  # Market closed
            pd.Timestamp("2023-01-04"),  # Market closed
            pd.Timestamp(
                "2022-12-30"
            ),  # Trading system maintenance, statistics and data migration
            pd.Timestamp("2021-01-08"),  # Trading platform security upgrade
            pd.Timestamp(
                "2021-12-31"
            ),  # Trading system maintenance, statistics and data migration
        ]
        return list(
            chain(
                misc_adhoc_holidays,
            )
        )
