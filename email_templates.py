"""Plain-text EN/AR bodies for system emails sent through the cloud relay.
Rendered cloud-side so sender branding stays consistent. Keep plain text —
OTP codes need no HTML, and plain text dodges RTL-HTML rendering bugs."""

_TEMPLATES = {
    'password_reset': {
        'en': ('Your {clinic_name} password reset code',
               'Your {clinic_name} password reset code is: {code}\n\n'
               'It expires in 10 minutes. If you did not request this, ignore this email.\n\n'
               '— DentaCare'),
        'ar': ('رمز إعادة تعيين كلمة المرور - {clinic_name}',
               'رمز إعادة تعيين كلمة المرور الخاص بـ {clinic_name} هو: {code}\n\n'
               'صالح لمدة 10 دقائق. إذا لم تطلب ذلك، تجاهل هذه الرسالة.\n\n'
               '— DentaCare'),
    },
    'email_verify': {
        'en': ('Verify your {clinic_name} email address',
               'Your {clinic_name} email verification code is: {code}\n\n'
               'It expires in 10 minutes. If you did not request this, ignore this email.\n\n'
               '— DentaCare'),
        'ar': ('تأكيد عنوان بريدك الإلكتروني - {clinic_name}',
               'رمز تأكيد البريد الإلكتروني الخاص بـ {clinic_name} هو: {code}\n\n'
               'صالح لمدة 10 دقائق. إذا لم تطلب ذلك، تجاهل هذه الرسالة.\n\n'
               '— DentaCare'),
    },
    'staff_invite': {
        'en': ('You have been invited to {clinic_name}',
               'You have been invited to {clinic_name}.\n'
               'Username: {username}\n'
               'Temporary sign-in code (use as your password once): {code}\n'
               'You will choose your own password on first sign-in.\n\n'
               '— DentaCare'),
        'ar': ('تمت دعوتك للانضمام إلى {clinic_name}',
               'تمت دعوتك للانضمام إلى {clinic_name}.\n'
               'اسم المستخدم: {username}\n'
               'رمز الدخول المؤقت (يُستخدم كلمة مرور لمرة واحدة): {code}\n'
               'ستقوم باختيار كلمة المرور الخاصة بك عند أول تسجيل دخول.\n\n'
               '— DentaCare'),
    },
    'security_alert': {
        'en': ('Security alert for {clinic_name}',
               'Security event at {clinic_name}: {event}\n{detail}\n'
               'If this was not you or your staff, reset the affected password now.\n\n'
               '— DentaCare'),
        'ar': ('تنبيه أمني - {clinic_name}',
               'حدث أمني في {clinic_name}: {event}\n{detail}\n'
               'إذا لم تكن أنت أو أحد أعضاء فريقك من قام بذلك، فأعد تعيين كلمة المرور المتأثرة فورًا.\n\n'
               '— DentaCare'),
    },
}


def render(template, lang, params):
    entry = _TEMPLATES.get(template)
    if entry is None:
        raise ValueError(f'unknown email template: {template!r}')
    subject, body = entry.get(lang) or entry['en']
    safe = {'clinic_name': '', 'code': '', 'username': '', 'event': '', 'detail': '',
            **(params or {})}
    return subject.format(**safe), body.format(**safe)
