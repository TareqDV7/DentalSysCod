import 'dart:convert';

/// A vendor-signed activation key, shaped `<payload>.<signature>` where both
/// parts are base64url. We read only the *public* payload (serial + clinic name)
/// to drive cloud registration; the cloud verifies the Ed25519 signature
/// authoritatively, so a tampered key is rejected server-side regardless.
class ActivationToken {
  const ActivationToken({required this.serial, this.clinicName, this.expiresAt});

  /// Clinic serial embedded in the key (upper-cased, >= 8 chars).
  final String serial;

  /// Clinic name embedded in the key, if any.
  final String? clinicName;

  /// ISO timestamp the license is valid until, embedded in the signed payload
  /// at mint time. Drives the "valid until" display; null when the key carries
  /// no expiry.
  final String? expiresAt;

  /// Parse [key]; returns null if it isn't a well-formed activation key.
  static ActivationToken? tryParse(String key) {
    final raw = key.trim();
    final dot = raw.indexOf('.');
    if (dot <= 0) return null;
    try {
      var payload = raw.substring(0, dot);
      final remainder = payload.length % 4;
      if (remainder != 0) {
        payload = payload + ('=' * (4 - remainder));
      }
      final decoded = jsonDecode(utf8.decode(base64Url.decode(payload)));
      if (decoded is! Map<String, dynamic>) return null;
      final serial = (decoded['serial'] ?? '').toString().trim();
      if (serial.length < 8) return null;
      final clinic =
          (decoded['clinic_name'] ?? decoded['clinic'] ?? '').toString().trim();
      final exp = (decoded['expires_at'] ?? '').toString().trim();
      return ActivationToken(
        serial: serial.toUpperCase(),
        clinicName: clinic.isEmpty ? null : clinic,
        expiresAt: exp.isEmpty ? null : exp,
      );
    } on FormatException {
      return null;
    }
  }
}
