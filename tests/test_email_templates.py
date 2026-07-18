import pytest

import email_templates


def test_reset_en_contains_code():
    subject, body = email_templates.render('password_reset', 'en',
                                           {'clinic_name': 'Smile Co', 'code': '123456'})
    assert '123456' in body and 'Smile Co' in body and subject


def test_reset_ar_is_arabic():
    subject, body = email_templates.render('password_reset', 'ar',
                                           {'clinic_name': 'X', 'code': '123456'})
    assert '123456' in body
    assert any('؀' <= ch <= 'ۿ' for ch in body)  # Arabic script present


def test_all_templates_both_langs():
    params = {'clinic_name': 'C', 'code': '000000', 'username': 'u',
              'event': 'password_changed', 'detail': 'x'}
    for t in ('password_reset', 'email_verify', 'staff_invite', 'security_alert'):
        for lang in ('en', 'ar'):
            subject, body = email_templates.render(t, lang, params)
            assert subject and body


def test_unknown_template_raises():
    with pytest.raises(ValueError):
        email_templates.render('nope', 'en', {})


def test_unknown_lang_falls_back_to_en():
    s_en, _ = email_templates.render('email_verify', 'en', {'clinic_name': 'C', 'code': '1'})
    s_xx, _ = email_templates.render('email_verify', 'fr', {'clinic_name': 'C', 'code': '1'})
    assert s_en == s_xx
