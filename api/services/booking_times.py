"""Minute-resolution arrival/departure values interpreted in Philippine time."""
from datetime import date, datetime, time, timezone, timedelta
import re

PHT = timezone(timedelta(hours=8))


def validate_booking_times(data, source='online', now=None):
    values = []
    for key in ('check_in_time', 'check_out_time'):
        value = data.get(key)
        if not isinstance(value, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value):
            raise ValueError('Choose both arrival and departure times.')
        values.append(value)
    try:
        arrival = datetime.combine(date.fromisoformat(data['check_in_date']), time.fromisoformat(values[0]), PHT)
        departure = datetime.combine(date.fromisoformat(data['check_out_date']), time.fromisoformat(values[1]), PHT)
    except (KeyError, TypeError, ValueError):
        raise ValueError('Choose valid arrival and departure dates and times.') from None
    if departure <= arrival or departure.date() <= arrival.date():
        raise ValueError('Departure must be on a later date. Rooms are priced per night.')
    if source == 'online' and arrival <= (now or datetime.now(timezone.utc)).astimezone(PHT):
        raise ValueError('Choose an arrival date and time in the future.')
    return values[0], values[1]
