/// ── Clinic Branding ─────────────────────────────────────────────────────────
/// Change these values to customise the app name, clinic, and doctor info.
/// One place to rebrand the entire app.
class AppBranding {
  static const String systemName = 'DentaCare';
  static const String clinicName = 'Dental Management System';
  static const String doctorName = 'Dr. Wasfy Barzaq';
  static const String doctorNameAr = 'د. وصفي برزق';
  static const String tagline = 'Patient Care & Practice Management';
  static const String appVersion = '1.0.0';
}
// ─────────────────────────────────────────────────────────────────────────────

class AppConfig {
  static const String defaultServerUrl = 'http://127.0.0.1:5000';

  static String normalizeBaseUrl(String value) {
    final trimmed = value.trim();
    if (trimmed.isEmpty) {
      return defaultServerUrl;
    }
    return trimmed.endsWith('/')
        ? trimmed.substring(0, trimmed.length - 1)
        : trimmed;
  }

  static String normalizeOrDefault(
    String? value, {
    String fallback = defaultServerUrl,
  }) {
    final candidate = value == null ? '' : value.trim();
    if (candidate.isEmpty) {
      return fallback;
    }
    return normalizeBaseUrl(candidate);
  }
}
