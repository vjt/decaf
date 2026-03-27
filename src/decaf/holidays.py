"""Italian public holidays and business day logic.

Used for the forex threshold analysis (art. 67(1)(c-ter) TUIR),
which counts consecutive business days excluding weekends and
Italian public holidays.
"""

from __future__ import annotations

from datetime import date, timedelta


def easter_sunday(year: int) -> date:
    """Compute Easter Sunday using the Anonymous Gregorian algorithm.

    https://en.wikipedia.org/wiki/Date_of_Easter#Anonymous_Gregorian_algorithm
    """
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def italian_holidays(year: int) -> set[date]:
    """Return the set of Italian public holidays for a given year.

    Includes all fixed national holidays and Easter-dependent holidays.
    """
    easter = easter_sunday(year)
    easter_monday = easter + timedelta(days=1)

    return {
        date(year, 1, 1),     # Capodanno
        date(year, 1, 6),     # Epifania
        easter,               # Pasqua
        easter_monday,        # Lunedì dell'Angelo
        date(year, 4, 25),    # Festa della Liberazione
        date(year, 5, 1),     # Festa del Lavoro
        date(year, 6, 2),     # Festa della Repubblica
        date(year, 8, 15),    # Ferragosto
        date(year, 11, 1),    # Tutti i Santi
        date(year, 12, 8),    # Immacolata Concezione
        date(year, 12, 25),   # Natale
        date(year, 12, 26),   # Santo Stefano
    }


def is_business_day(d: date, holidays: set[date] | None = None) -> bool:
    """Check if a date is an Italian business day.

    A business day is Monday-Friday and not an Italian public holiday.
    """
    if d.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    if holidays is None:
        holidays = italian_holidays(d.year)
    return d not in holidays


def count_business_days(start: date, end: date, holidays: set[date] | None = None) -> int:
    """Count business days in [start, end] inclusive."""
    if holidays is None:
        holidays = italian_holidays(start.year)
        if start.year != end.year:
            holidays = holidays | italian_holidays(end.year)

    count = 0
    current = start
    while current <= end:
        if is_business_day(current, holidays):
            count += 1
        current += timedelta(days=1)
    return count
