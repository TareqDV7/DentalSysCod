"""Email and SMS senders for appointment reminders. stdlib only
(smtplib + urllib.request) — no new third-party HTTP/SMS SDK dependency,
matching this codebase's existing stdlib-first convention for outbound
HTTP (see dental_clinic.py's _cloud_http_request)."""
import base64
import smtplib
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage


class ReminderSendError(Exception):
    """Raised on any failure to deliver a reminder — the dispatch loop
    catches this, logs a 'failed' row, and moves on to the next reminder."""


def send_email(to: str, subject: str, body: str, smtp_cfg: dict) -> None:
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = smtp_cfg['user']
    msg['To'] = to
    msg.set_content(body)
    try:
        with smtplib.SMTP(smtp_cfg['host'], smtp_cfg['port'], timeout=15) as server:
            server.starttls()
            server.login(smtp_cfg['user'], smtp_cfg['password'])
            server.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        raise ReminderSendError(f'email send failed: {exc}') from exc


def _send_sms_twilio(to: str, body: str, sms_cfg: dict) -> None:
    account_sid = sms_cfg['api_key']
    auth_token = sms_cfg['api_secret']
    url = f'https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json'
    payload = urllib.parse.urlencode({
        'To': to,
        'From': sms_cfg['from_number'],
        'Body': body,
    }).encode('utf-8')
    basic_auth = base64.b64encode(f'{account_sid}:{auth_token}'.encode('utf-8')).decode('ascii')
    req = urllib.request.Request(
        url, data=payload,
        headers={
            'Authorization': f'Basic {basic_auth}',
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status >= 300:
                raise ReminderSendError(f'Twilio returned status {resp.status}')
    except urllib.error.HTTPError as exc:
        raise ReminderSendError(f'Twilio HTTP error {exc.code}: {exc.reason}') from exc
    except urllib.error.URLError as exc:
        raise ReminderSendError(f'Twilio connection failed: {exc.reason}') from exc


_SMS_PROVIDERS = {
    'twilio': _send_sms_twilio,
}


def send_sms(to: str, body: str, sms_cfg: dict) -> None:
    provider = sms_cfg.get('provider')
    sender = _SMS_PROVIDERS.get(provider)
    if sender is None:
        raise ReminderSendError(f'unknown SMS provider: {provider!r}')
    sender(to, body, sms_cfg)
