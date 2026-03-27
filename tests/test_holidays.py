"""Tests for Italian holidays and business day logic."""

from datetime import date

from ibtax.holidays import (
    count_business_days,
    easter_sunday,
    is_business_day,
    italian_holidays,
)


class TestEasterSunday:
    def test_2025(self) -> None:
        assert easter_sunday(2025) == date(2025, 4, 20)

    def test_2026(self) -> None:
        assert easter_sunday(2026) == date(2026, 4, 5)

    def test_2024(self) -> None:
        assert easter_sunday(2024) == date(2024, 3, 31)

    def test_2023(self) -> None:
        assert easter_sunday(2023) == date(2023, 4, 9)


class TestItalianHolidays:
    def test_2025_fixed_holidays(self) -> None:
        holidays = italian_holidays(2025)
        assert date(2025, 1, 1) in holidays    # Capodanno
        assert date(2025, 1, 6) in holidays    # Epifania
        assert date(2025, 4, 25) in holidays   # Liberazione
        assert date(2025, 5, 1) in holidays    # Lavoro
        assert date(2025, 6, 2) in holidays    # Repubblica
        assert date(2025, 8, 15) in holidays   # Ferragosto
        assert date(2025, 11, 1) in holidays   # Tutti i Santi
        assert date(2025, 12, 8) in holidays   # Immacolata
        assert date(2025, 12, 25) in holidays  # Natale
        assert date(2025, 12, 26) in holidays  # Santo Stefano

    def test_2025_easter(self) -> None:
        holidays = italian_holidays(2025)
        assert date(2025, 4, 20) in holidays   # Easter Sunday
        assert date(2025, 4, 21) in holidays   # Easter Monday

    def test_count(self) -> None:
        assert len(italian_holidays(2025)) == 12

    def test_regular_day_not_holiday(self) -> None:
        holidays = italian_holidays(2025)
        assert date(2025, 3, 15) not in holidays


class TestIsBusinessDay:
    def test_monday(self) -> None:
        # 2025-09-01 is a Monday
        assert is_business_day(date(2025, 9, 1))

    def test_friday(self) -> None:
        # 2025-09-05 is a Friday
        assert is_business_day(date(2025, 9, 5))

    def test_saturday(self) -> None:
        # 2025-09-06 is a Saturday
        assert not is_business_day(date(2025, 9, 6))

    def test_sunday(self) -> None:
        # 2025-09-07 is a Sunday
        assert not is_business_day(date(2025, 9, 7))

    def test_holiday_on_weekday(self) -> None:
        # 2025-04-25 is Friday (Liberazione)
        assert not is_business_day(date(2025, 4, 25))

    def test_christmas(self) -> None:
        # 2025-12-25 is Thursday
        assert not is_business_day(date(2025, 12, 25))


class TestCountBusinessDays:
    def test_full_week(self) -> None:
        # Mon Sep 1 to Fri Sep 5 = 5 business days
        assert count_business_days(date(2025, 9, 1), date(2025, 9, 5)) == 5

    def test_includes_weekend(self) -> None:
        # Mon Sep 1 to Mon Sep 8 = 6 business days (skip Sat+Sun)
        assert count_business_days(date(2025, 9, 1), date(2025, 9, 8)) == 6

    def test_single_day_business(self) -> None:
        assert count_business_days(date(2025, 9, 1), date(2025, 9, 1)) == 1

    def test_single_day_weekend(self) -> None:
        assert count_business_days(date(2025, 9, 6), date(2025, 9, 6)) == 0

    def test_week_with_holiday(self) -> None:
        # Apr 21-25 2025: Mon is Easter Monday (holiday), Fri is Liberazione (holiday)
        # Tue=22, Wed=23, Thu=24 are business days → 3
        assert count_business_days(date(2025, 4, 21), date(2025, 4, 25)) == 3
