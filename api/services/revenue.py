"""Staff-only reporting of recorded receipts, using centavo-safe arithmetic."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

PHT = timezone(timedelta(hours=8))


def revenue_summary(query, now=None):
    now = (now or datetime.now(timezone.utc)).astimezone(PHT)
    month_index = now.year * 12 + now.month - 1
    buckets = {}
    for index in range(month_index - 11, month_index + 1):
        year, month = divmod(index, 12)
        buckets[f'{year:04d}-{month + 1:02d}'] = {'room_payments': 0, 'service_payments': 0}
    first = now.replace(year=(month_index - 11) // 12, month=(month_index - 11) % 12 + 1,
                        day=1, hour=0, minute=0, second=0, microsecond=0)
    start = quote(first.astimezone(timezone.utc).isoformat(), safe='')
    end = quote(now.astimezone(timezone.utc).isoformat(), safe='')
    for table, field in [('booking_payments', 'room_payments'), ('service_payments', 'service_payments')]:
        offset = 0
        while True:
            rows = query(f'{table}?select=id,amount,created_at&created_at=gte.{start}&created_at=lte.{end}&order=id.asc&limit=500&offset={offset}')
            if not isinstance(rows, list):
                raise RuntimeError('Receipt ledger unavailable')
            if not rows:
                break
            for row in rows:
                try:
                    amount = Decimal(str(row['amount']))
                    when = datetime.fromisoformat(row['created_at'].replace('Z', '+00:00'))
                    if when.tzinfo is None or not amount.is_finite() or amount <= 0 or amount != amount.quantize(Decimal('.01')):
                        raise ValueError('Invalid receipt')
                    local = when.astimezone(PHT)
                    if first <= local <= now:
                        buckets[local.strftime('%Y-%m')][field] += int(amount * 100)
                except (KeyError, TypeError, ValueError, InvalidOperation):
                    raise RuntimeError('Invalid receipt data') from None
            offset += len(rows)
    months = []
    for month, values in buckets.items():
        months.append({'month': month, **{key: float(Decimal(amount) / 100) for key, amount in values.items()},
                       'total': float(Decimal(sum(values.values())) / 100)})
    return {'currency': 'PHP', 'timezone': 'Asia/Manila', 'basis': 'recorded_receipts_before_refunds',
            'as_of': now.isoformat(), 'months': months}
