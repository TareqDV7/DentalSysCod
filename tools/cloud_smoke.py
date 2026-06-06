#!/usr/bin/env python3
"""Live cloud-node smoke test for the Ed25519 license authority.

Exercises the deployed cloud node end-to-end against a throwaway serial:

    register  ->  validate (first use)  ->  validate (idempotent re-claim)
    ->  device-cap enforcement  ->  admin release  ->  admin revoke
    ->  validate (rejected)  ->  admin reactivate

Nothing here is destructive to real data: it provisions ONE throwaway clinic +
serial and prints the cleanup SQL at the end (the cloud has no delete API).

Usage
-----
Mint a token locally (vendor machine holding the private seed):

    python tools/cloud_smoke.py \
        --base-url https://app.dentacare.tech \
        --key-file backend_ed25519_key.json \
        --admin-token "$CLINIC_ADMIN_API_TOKEN"

Or supply a pre-minted token (when the private seed is NOT on this machine —
mint one in the serial_admin console and paste it):

    python tools/cloud_smoke.py --token '<offline_token>' --admin-token '...'

The admin token is read from --admin-token or the CLINIC_ADMIN_API_TOKEN env.
Without it, the revoke/release steps are skipped (not failed) with a notice.

Exit code 0 = every checked step met expectations; 1 = at least one mismatch.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

# Import the vendor signing helpers from the repo root (this file lives in tools/).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

DEFAULT_BASE_URL = 'https://app.dentacare.tech'
DEFAULT_KEY_FILE = os.path.join(_REPO_ROOT, 'backend_ed25519_key.json')
HTTP_TIMEOUT = 15  # seconds


# --------------------------------------------------------------------------- #
# Result tracking
# --------------------------------------------------------------------------- #
class Report:
    """Collects pass/fail/skip lines and prints a summary."""

    def __init__(self):
        self.rows = []  # (state, name, detail) where state in {ok, fail, skip}

    def ok(self, name, detail=''):
        self.rows.append(('ok', name, detail))
        print(f'  [PASS] {name}{" — " + detail if detail else ""}')

    def fail(self, name, detail=''):
        self.rows.append(('fail', name, detail))
        print(f'  [FAIL] {name}{" — " + detail if detail else ""}')

    def skip(self, name, detail=''):
        self.rows.append(('skip', name, detail))
        print(f'  [SKIP] {name}{" — " + detail if detail else ""}')

    def expect(self, name, condition, detail=''):
        (self.ok if condition else self.fail)(name, detail)
        return condition

    @property
    def failed(self):
        return any(state == 'fail' for state, _, _ in self.rows)

    def summary(self):
        n_ok = sum(1 for s, _, _ in self.rows if s == 'ok')
        n_fail = sum(1 for s, _, _ in self.rows if s == 'fail')
        n_skip = sum(1 for s, _, _ in self.rows if s == 'skip')
        print('\n' + '=' * 60)
        print(f'RESULT: {n_ok} passed, {n_fail} failed, {n_skip} skipped')
        print('=' * 60)


# --------------------------------------------------------------------------- #
# HTTP helper
# --------------------------------------------------------------------------- #
def post_json(base_url, path, body, headers=None):
    """POST JSON; return (status_code, parsed_body_or_text). Never raises on HTTP
    error status — reads the error body so the caller can assert on it."""
    url = base_url.rstrip('/') + path
    data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return resp.status, _parse(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, _parse(exc.read())
    except urllib.error.URLError as exc:
        return None, {'_error': f'network error: {exc.reason}'}


def get_json(base_url, path):
    url = base_url.rstrip('/') + path
    try:
        with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT) as resp:
            return resp.status, _parse(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, _parse(exc.read())
    except urllib.error.URLError as exc:
        return None, {'_error': f'network error: {exc.reason}'}


def _parse(raw):
    try:
        return json.loads(raw.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return {'_raw': raw[:300].decode('utf-8', 'replace')}


# --------------------------------------------------------------------------- #
# Token acquisition
# --------------------------------------------------------------------------- #
def mint_token(serial, key_file, max_devices):
    """Mint a signed offline token using the vendor private seed."""
    import serial_generator
    seed = serial_generator.load_private_seed(key_file)
    result = serial_generator.generate_license_token(
        serial=serial, clinic_name='SMOKE TEST CLINIC', device_id='smoke',
        plan_name='Standard', max_devices=max_devices, expiry_days=365,
        private_seed_b64=seed,
    )
    return result['offline_token']


def serial_from_token(token):
    """Decode the (unverified) payload to read its serial — for the --token path."""
    import serial_generator
    payload_part = token.split('.', 1)[0]
    payload = json.loads(serial_generator._b64u_decode(payload_part).decode('utf-8'))
    return str(payload.get('serial') or '').strip().upper()


# --------------------------------------------------------------------------- #
# Main flow
# --------------------------------------------------------------------------- #
def run(args):
    rep = Report()
    base = args.base_url

    # 0) Acquire a signed token + serial.
    if args.token:
        token = args.token.strip()
        try:
            serial = args.serial or serial_from_token(token)
        except Exception as exc:  # noqa: BLE001
            print(f'Could not decode --token payload: {exc}')
            return 1
        print(f'Using supplied token; serial = {serial}')
    else:
        serial = args.serial or f'SMOKE-{int(time.time())}'
        if not os.path.exists(args.key_file):
            print(f'No --token given and key file not found: {args.key_file}\n'
                  f'Either pass --token <offline_token> or --key-file <path to '
                  f'backend_ed25519_key.json>.')
            return 1
        try:
            token = mint_token(serial, args.key_file, args.max_devices)
        except Exception as exc:  # noqa: BLE001
            print(f'Failed to mint token: {exc}')
            return 1
        print(f'Minted signed token for serial = {serial} (max_devices={args.max_devices})')

    fp1, fp2, fp3 = (f'smoke-fp-{serial}-{n}' for n in (1, 2, 3))

    print('\n--- health ---')
    status, body = get_json(base, '/healthz')
    rep.expect('GET /healthz reachable', status == 200,
               f'status={status} mode={body.get("mode")}' if isinstance(body, dict) else f'status={status}')

    print('\n--- register ---')
    status, body = post_json(base, '/api/clinics/register',
                             {'serial_number': serial, 'clinic_name': 'SMOKE TEST CLINIC',
                              'offline_token': token})
    clinic_id = body.get('clinic_id') if isinstance(body, dict) else None
    rep.expect('register returns 200 + success', status == 200 and bool(body.get('success')),
               f'status={status} clinic_id={clinic_id} already={body.get("already_registered")} '
               f'err={body.get("error")}')

    print('\n--- validate (first use claims a slot) ---')
    status, body = post_json(base, '/api/license/validate',
                             {'serial_token': token, 'device_fingerprint': fp1,
                              'device_name': 'smoke-1'})
    rep.expect('validate fp1 -> valid', status == 200 and body.get('valid') is True,
               f'status={status} reason={body.get("reason")} remaining={body.get("remaining_slots")}')

    print('\n--- validate (same fp -> idempotent re-claim) ---')
    status, body2 = post_json(base, '/api/license/validate',
                              {'serial_token': token, 'device_fingerprint': fp1,
                               'device_name': 'smoke-1'})
    rep.expect('validate fp1 again -> still valid, no extra slot used',
               status == 200 and body2.get('valid') is True
               and body2.get('remaining_slots') == body.get('remaining_slots'),
               f'remaining={body2.get("remaining_slots")} (was {body.get("remaining_slots")})')

    print('\n--- device-cap enforcement ---')
    # max_devices defaults to 2 for the smoke: fp2 fills it, fp3 should be rejected.
    status, body = post_json(base, '/api/license/validate',
                             {'serial_token': token, 'device_fingerprint': fp2, 'device_name': 'smoke-2'})
    fp2_ok = status == 200 and body.get('valid') is True
    rep.expect('validate fp2 -> valid (fills cap)', fp2_ok,
               f'reason={body.get("reason")} remaining={body.get("remaining_slots")}')
    status, body = post_json(base, '/api/license/validate',
                             {'serial_token': token, 'device_fingerprint': fp3, 'device_name': 'smoke-3'})
    rep.expect('validate fp3 -> rejected (device_cap_reached)',
               status == 200 and body.get('valid') is False and body.get('reason') == 'device_cap_reached',
               f'valid={body.get("valid")} reason={body.get("reason")}')

    admin = args.admin_token or os.environ.get('CLINIC_ADMIN_API_TOKEN', '')
    admin = admin.strip()
    if not admin:
        rep.skip('admin release fp2', 'no --admin-token / CLINIC_ADMIN_API_TOKEN')
        rep.skip('admin revoke serial', 'no admin token')
        rep.skip('validate after revoke', 'no admin token')
        rep.skip('admin reactivate', 'no admin token')
    else:
        hdr = {'X-Admin-Token': admin}

        print('\n--- admin: release fp2, then fp3 fits ---')
        status, body = post_json(base, '/api/license/admin/revoke',
                                 {'serial': serial, 'release': True, 'device_fingerprint': fp2}, hdr)
        rep.expect('admin release fp2 -> success', status == 200 and bool(body.get('success')),
                   f'status={status} err={body.get("error")}')
        status, body = post_json(base, '/api/license/validate',
                                 {'serial_token': token, 'device_fingerprint': fp3, 'device_name': 'smoke-3'})
        rep.expect('validate fp3 -> now valid (freed slot)',
                   status == 200 and body.get('valid') is True,
                   f'reason={body.get("reason")} remaining={body.get("remaining_slots")}')

        print('\n--- admin: revoke serial ---')
        status, body = post_json(base, '/api/license/admin/revoke', {'serial': serial}, hdr)
        rep.expect('admin revoke -> success', status == 200 and bool(body.get('success')),
                   f'status={status} err={body.get("error")}')
        status, body = post_json(base, '/api/license/validate',
                                 {'serial_token': token, 'device_fingerprint': fp1, 'device_name': 'smoke-1'})
        rep.expect('validate after revoke -> rejected (revoked)',
                   status == 200 and body.get('valid') is False and body.get('reason') == 'revoked',
                   f'valid={body.get("valid")} reason={body.get("reason")}')

        print('\n--- admin: wrong token is rejected ---')
        status, body = post_json(base, '/api/license/admin/revoke', {'serial': serial},
                                 {'X-Admin-Token': admin + 'x'})
        rep.expect('revoke with wrong admin token -> 401', status == 401,
                   f'status={status}')

        print('\n--- admin: reactivate (leave serial active) ---')
        status, body = post_json(base, '/api/license/admin/revoke',
                                 {'serial': serial, 'status': 'active'}, hdr)
        rep.expect('admin reactivate -> success', status == 200 and bool(body.get('success')),
                   f'status={status} err={body.get("error")}')

    rep.summary()

    print('\nCleanup (the cloud has no delete API — run on the droplet to remove '
          'the throwaway tenant):')
    print('  ssh root@<droplet>')
    print("  docker compose -f /opt/dentacare/cloud/docker-compose.yml exec -T app \\")
    print("    python -c \"import sqlite3,os; c=sqlite3.connect(os.environ['CLINIC_DATA_DIR']+'/cloud_master.db'); "
          f"[c.execute(q,('{serial}',)) for q in "
          "('DELETE FROM clinics WHERE serial_number=?','DELETE FROM license_serials WHERE serial=?',"
          "'DELETE FROM license_device_slots WHERE serial=?')]; c.commit()\"")
    if clinic_id:
        print(f'  # then remove the tenant DB:  rm /data/clinic_{clinic_id}.db  (inside the dentacare-data volume)')

    return 1 if rep.failed else 0


def main():
    p = argparse.ArgumentParser(description='Live cloud-node license-authority smoke test.')
    p.add_argument('--base-url', default=DEFAULT_BASE_URL,
                   help=f'cloud node base URL (default: {DEFAULT_BASE_URL})')
    p.add_argument('--key-file', default=DEFAULT_KEY_FILE,
                   help='vendor Ed25519 private-seed JSON to mint a token '
                        '(default: backend_ed25519_key.json in repo root)')
    p.add_argument('--token', default='',
                   help='pre-minted offline_token (use instead of --key-file when the '
                        'private seed is not on this machine)')
    p.add_argument('--serial', default='',
                   help='serial to use (default: a unique SMOKE-<timestamp>)')
    p.add_argument('--admin-token', default='',
                   help='X-Admin-Token for the revoke/release steps '
                        '(falls back to the CLINIC_ADMIN_API_TOKEN env var)')
    p.add_argument('--max-devices', type=int, default=2,
                   help='device cap baked into the minted token (default 2, to test the cap)')
    args = p.parse_args()
    try:
        sys.exit(run(args))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == '__main__':
    main()
