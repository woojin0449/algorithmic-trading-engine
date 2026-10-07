from datetime import time
from zoneinfo import ZoneInfo

from pandas.tseries.holiday import (
    Holiday,
    GoodFriday,
    EasterMonday,
)

from .common_holidays import (
    new_years_day,
    assumption_day,
    christmas_eve,
    christmas,
    boxing_day,
    new_years_eve,
)
from .exchange_calendar import HolidayCalendar, ExchangeCalendar

NewYearsDay = new_years_day()
NewYearHoliday = Holiday("New Year Holiday", month=1, day=2, start_date="2017")
NewYearHolidayBefore2013 = Holiday("New Year Holiday", month=1, day=2, end_date="2013")
PreserenDay = Holiday("Prešeren Day", month=2, day=8)
ResistanceDay = Holiday("Resistance Day", month=4, day=27)
LabourDay = Holiday("Labour Day", month=5, day=1)
LabourDay2 = Holiday("Labour Day (Second Day)", month=5, day=2)
StatehoodDay = Holiday("Statehood Day", month=6, day=25)
AssumptionDay = assumption_day()
ReformationDay = Holiday("Reformation Day", month=10, day=31)
AllSaintsDay = Holiday("All Saints' Day", month=11, day=1)
ChristmasEve = christmas_eve()
Christmas = christmas()
IndependenceUnityDay = Holiday("Independence and Unity Day", month=12, day=26)
BoxingDay = boxing_day()
NewYearsEve = new_years_eve()


class XLJUExchangeCalendar(ExchangeCalendar):
    """
    Calendar for the Ljubljana Stock Exchange (Slovenia).
    https://ljse.si/en/non-trading-days/110

    Open Time: 9:15 AM
    Close Time: 3:15 PM

    Regularly-Observed Holidays:
      - New Year's Day (Jan 1)
      - New Year Holiday (Jan 2)
      - Prešeren Day (Feb 8)
      - Good Friday
      - Easter Monday
      - Resistance Day (Apr 27)
      - Labour Day (May 1 & 2)
      - National Holiday (Jun 25)
      - Assumption Day (Aug 15)
      - Reformation Day (Oct 31)
      - All Saints' Day (Nov 1)
      - Christmas Eve (Dec 24)
      - Christmas Day (Dec 25)
      - Independence and Unity Day (Dec 26)
      - New Years Eve (Dec 31)
    """

    name = "XLJU"
    tz = ZoneInfo("Europe/Ljubljana")
    open_times = ((None, time(9, 15)),)
    close_times = ((None, time(15, 15)),)

    @property
    def regular_holidays(self):
        return HolidayCalendar(
            [
                NewYearsDay,
                NewYearHoliday,
                NewYearHolidayBefore2013,
                PreserenDay,
                GoodFriday,
                EasterMonday,
                ResistanceDay,
                LabourDay,
                LabourDay2,
                StatehoodDay,
                AssumptionDay,
                ReformationDay,
                AllSaintsDay,
                ChristmasEve,
                Christmas,
                IndependenceUnityDay,
                NewYearsEve,
            ]
        )

    @property
    def adhoc_holidays(self):
        return [
            "2023-08-14",  # Day off work due to the floods
            "2017-02-02",
            "2017-02-03",
        ]
