"""Exact room rating counts without exposing review/account records."""
from concurrent.futures import ThreadPoolExecutor
import re
import requests


def rating_summary(base_url, key, room_id=None):
    def count(star):
        params = {'select': 'id', 'rating': f'eq.{star}', 'limit': '0'}
        if room_id is not None:
            params['room_id'] = f'eq.{room_id}'
        response = requests.head(base_url.rstrip('/') + '/rest/v1/reviews', params=params,
                                 headers={'apikey': key, 'Authorization': 'Bearer ' + key,
                                          'Prefer': 'count=exact'}, timeout=8)
        if not response.ok:
            raise RuntimeError('Review counts unavailable')
        match = re.fullmatch(r'.*/(\d+)', response.headers.get('Content-Range', ''))
        if not match:
            raise RuntimeError('Review count missing')
        return star, int(match.group(1))

    with ThreadPoolExecutor(max_workers=5) as pool:
        counts = dict(pool.map(count, range(1, 6)))
    total = sum(counts.values())
    return {'rating_breakdown': {str(star): counts[star] for star in range(5, 0, -1)},
            'total_reviews': total,
            'average_rating': round(sum(star * amount for star, amount in counts.items()) / total, 2) if total else 0}
