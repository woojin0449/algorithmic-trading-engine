from datetime import time
from zoneinfo import ZoneInfo

import pandas as pd
from pandas.tseries.holiday import (
    Holiday,
    EasterMonday,
    GoodFriday,
)
from .common_holidays import (
    new_years_day,
    epiphany,
    european_labour_day,
    all_saints_day,
    christmas_eve,
    christmas,
    boxing_day,
    new_years_eve,
)
from .exchange_calendar import HolidayCalendar, ExchangeCalendar

NewYearsDay = new_years_day()
Epiphany = epiphany()
LabourDay = european_labour_day()
VictoryDay = Holiday("Victory Day", month=5, day=8)
SaintsCyrilMethodius = Holiday("Saints Cyril and Methodius Day", month=7, day=5)
SlovakNationalUprising = Holiday(
    "Slovak National Uprising Anniversary", month=8, day=29
)
ConstitutionDay = Holiday("Constitution Day", month=9, day=1, end_date="2024")
VirginMary = Holiday("Day of Our Lady of Sorrows", month=9, day=15)
AllSaintsDay = all_saints_day()
StruggleForFreedom = Holiday("Struggle for Freedom and Democracy Day", month=11, day=17)
ChristmasEve = christmas_eve()
Christmas = christmas()
BoxingDay = boxing_day()
NewYearsEve = new_years_eve(start_date="2016")


class XBRAExchangeCalendar(ExchangeCalendar):
    """
    Calendar for the Bratislava Stock Exchange (Slovakia).
    https://www.bsse.sk/bcpb/en/trading-days/

    Open Time: 11:00 AM
    Close Time: 3:30 PM

    Regularly-Observed Holidays:
      - New Year's Day (Jan 1)
      - Epiphany (Jan 6)
      - Good Friday
      - Easter Monday
      - Labour Day (May 1)
      - Victory Day (May 8)
      - Saints Cyril and Methodius Day (Jul 5)
      - Slovak National Uprising Anniversary (Aug 29)
      - Constitution Day (Sep 1)
      - Day of Our Lady of Sorrows (Sep 15)
      - All Saints' Day (Nov 1)
      - Struggle for Freedom and Democracy Day (Nov 17)
      - Christmas Eve (Dec 24)
      - Christmas Day (Dec 25)
      - Boxing Day (Dec 26)
      - New Year's Eve (Dec 31)
    """

    name = "XBRA"
    tz = ZoneInfo("Europe/Bratislava")
    open_times = ((None, time(11, 00)),)
    close_times = ((None, time(15, 30)),)

    @property
    def regular_holidays(self):
        return HolidayCalendar(
            [
                NewYearsDay,
                Epiphany,
                GoodFriday,
                EasterMonday,
                LabourDay,
                VictoryDay,
                SaintsCyrilMethodius,
                SlovakNationalUprising,
                ConstitutionDay,
                VirginMary,
                AllSaintsDay,
                StruggleForFreedom,
                ChristmasEve,
                Christmas,
                BoxingDay,
                NewYearsEve,
            ]
        )

    @property
    def adhoc_holidays(self):
        return [
            pd.Timestamp("2018-01-02"),  # Independent Slovakia, 25th anniversary
            pd.Timestamp(
                "2018-10-30"
            ),  # 100th anniversary of the adoption of the Declaration of
            # the Slovak Nation
        ]
