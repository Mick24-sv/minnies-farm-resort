"""One-time, explicitly authorized password-format repair. Dry-run by default.

No passwords, hashes, tokens, or email addresses are written to files or output.
Only password fields of legacy-format accounts can be changed.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from threading import Thread

import requests
from dotenv import load_dotenv
from passlib.hash import pbkdf2_sha256

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def is_legacy_plaintext(value):
    if not isinstance(value, str) or not value or len(value) > 256:
        return False
    if value.startswith(('$', '{', 'scrypt:', 'pbkdf2:', 'argon2:', 'bcrypt:')):
        return False
    if re.fullmatch(r'[0-9a-fA-F]{32}|[0-9a-fA-F]{40}|[0-9a-fA-F]{64}|[0-9a-fA-F]{128}', value):
        return False
    return value.isprintable()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--expected-count', type=int, default=2)
    parser.add_argument('--browser-check', action='store_true')
    args = parser.parse_args()
    load_dotenv(ROOT / '.env')
    base = os.environ['SUPABASE_URL'].strip().rstrip('/') + '/rest/v1/users'
    key = os.environ['SUPABASE_KEY'].strip()
    headers = {'apikey': key, 'Authorization': 'Bearer ' + key}

    def read(params):
        response = requests.get(base, params=params, headers=headers, timeout=15)
        if not response.ok:
            raise RuntimeError('Account read failed (HTTP %s).' % response.status_code)
        return response.json()

    before = read({'select': 'id,email,role,password'})
    candidates = [row for row in before if is_legacy_plaintext(row.get('password'))]
    unsupported = [row for row in before if not pbkdf2_sha256.identify(row.get('password') or '') and row not in candidates]
    print(json.dumps({'mode': 'apply' if args.apply else 'dry-run', 'accounts': len(before),
                      'legacy_candidates': len(candidates), 'unsupported_formats': len(unsupported),
                      'candidate_roles': [row['role'] for row in candidates]}), flush=True)
    if not args.apply:
        return
    if unsupported or len(candidates) != args.expected_count:
        raise RuntimeError('Account formats/count changed. No changes were made.')
    if sorted(row['role'] for row in candidates) != ['guest', 'staff']:
        raise RuntimeError('Expected one staff and one guest account. No changes were made.')

    for row in candidates:
        current = read({'id': 'eq.' + str(int(row['id'])), 'select': 'id,email,role,password'})
        if len(current) != 1 or current[0] != row:
            raise RuntimeError('Account changed during review; stopped without overwriting it.')
        new_hash = pbkdf2_sha256.using(rounds=600000).hash(row['password'])
        response = requests.patch(base, params={'id': 'eq.' + str(int(row['id'])), 'select': 'id'},
                                  headers={**headers, 'Prefer': 'return=representation'},
                                  json={'password': new_hash}, timeout=15)
        if not response.ok or response.json() != [{'id': row['id']}]:
            raise RuntimeError('Password update could not be confirmed. Stop and review before retrying.')

    after = read({'select': 'id,email,role,password'})
    by_id = {row['id']: row for row in after}
    candidate_ids = {row['id'] for row in candidates}
    if len(before) != len(after):
        raise RuntimeError('Account count changed during migration.')
    for row in before:
        current = by_id[row['id']]
        if (row['email'], row['role']) != (current['email'], current['role']):
            raise RuntimeError('Account identity or role changed during migration.')
        if row['id'] in candidate_ids:
            if not pbkdf2_sha256.verify(row['password'], current['password']):
                raise RuntimeError('Migrated password verification failed.')
        elif row['password'] != current['password']:
            raise RuntimeError('An unrelated password changed during migration.')
    print('PASS: two password fields repaired; all account identities, roles, and other passwords preserved.', flush=True)

    # Test real login/identity routes, but never deliver queued email or mutate bookings.
    os.environ['SENDGRID_API_KEY'] = ''
    os.environ['FROM_EMAIL'] = ''
    from api.index import app
    app.config['DEBUG'] = False
    client = app.test_client()
    for row in candidates:
        result = client.post('/api/auth/login', json={'email': row['email'], 'password': row['password']})
        payload = result.get_json()
        if result.status_code != 200 or payload.get('user', {}).get('role') != row['role']:
            raise RuntimeError('Live login verification failed for a repaired account.')
        identity = client.get('/api/auth/me', headers={'Authorization': 'Bearer ' + payload['token']})
        if identity.status_code != 200 or identity.get_json()['user']['id'] != row['id']:
            raise RuntimeError('Live session identity verification failed.')
        print('PASS: live %s login and authenticated identity.' % row['role'], flush=True)

    if args.browser_check:
        from werkzeug.serving import make_server
        server = make_server('127.0.0.1', 5012, app, threaded=True)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        staff = next(row for row in candidates if row['role'] == 'staff')
        try:
            result = subprocess.run(['node', str(ROOT / 'tests/frontend/staff-login-live.cjs')],
                                    input=json.dumps({'email': staff['email'], 'password': staff['password']}),
                                    text=True, capture_output=True, cwd=ROOT, timeout=90)
            if result.returncode:
                raise RuntimeError('Staff browser verification failed; account migration remains verified by API.')
            print(result.stdout.strip(), flush=True)
        finally:
            server.shutdown()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Do not echo request URLs, request bodies, or exception values containing secrets.
        print('Migration stopped (%s). Review the last completed verification step.' % type(error).__name__, file=sys.stderr)
        sys.exit(1)
