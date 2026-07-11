"""Email (stdlib smtplib) and SMS (Twilio REST, stdlib urllib) senders.
No real network calls — smtplib.SMTP and urllib.request.urlopen are mocked."""
import smtplib
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

import reminder_channels


SMTP_CFG = {'host': 'smtp.example.com', 'port': 587, 'user': 'clinic@example.com', 'password': 'secret'}
SMS_CFG = {'provider': 'twilio', 'api_key': 'ACxxxx', 'api_secret': 'authtoken', 'from_number': '+15551234567'}


def test_send_email_success():
    mock_smtp = MagicMock()
    with patch('smtplib.SMTP', return_value=mock_smtp) as ctor:
        mock_smtp.__enter__.return_value = mock_smtp
        reminder_channels.send_email('patient@example.com', 'Reminder', 'See you soon', SMTP_CFG)
    ctor.assert_called_once_with('smtp.example.com', 587, timeout=15)
    mock_smtp.starttls.assert_called_once()
    mock_smtp.login.assert_called_once_with('clinic@example.com', 'secret')
    mock_smtp.send_message.assert_called_once()


def test_send_email_raises_reminder_send_error_on_smtp_failure():
    with patch('smtplib.SMTP', side_effect=smtplib.SMTPException('auth failed')):
        with pytest.raises(reminder_channels.ReminderSendError):
            reminder_channels.send_email('patient@example.com', 'Reminder', 'body', SMTP_CFG)


def test_send_sms_success():
    fake_resp = MagicMock()
    fake_resp.status = 201
    fake_resp.read.return_value = b'{"sid": "SMxxxx"}'
    fake_resp.__enter__.return_value = fake_resp
    with patch('urllib.request.urlopen', return_value=fake_resp) as urlopen:
        reminder_channels.send_sms('+15559876543', 'See you soon', SMS_CFG)
    assert urlopen.called
    req = urlopen.call_args[0][0]
    assert 'ACxxxx' in req.full_url


def test_send_sms_raises_reminder_send_error_on_http_error():
    err = urllib.error.HTTPError('url', 401, 'Unauthorized', {}, None)
    with patch('urllib.request.urlopen', side_effect=err):
        with pytest.raises(reminder_channels.ReminderSendError):
            reminder_channels.send_sms('+15559876543', 'body', SMS_CFG)


def test_send_sms_raises_on_unknown_provider():
    with pytest.raises(reminder_channels.ReminderSendError):
        reminder_channels.send_sms('+15559876543', 'body', {**SMS_CFG, 'provider': 'unknown_co'})
