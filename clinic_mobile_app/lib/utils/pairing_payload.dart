import 'dart:convert';

/// The decoded contents of a desktop pairing QR.
///
/// The desktop renders `{"v":1,"u":<cloud_url>,"t":<clinic_token>}` as a QR; the
/// phone scans it and links by token (no `/api/clinics/register` round-trip).
class PairingPayload {
  const PairingPayload({required this.cloudUrl, required this.clinicToken});

  final String cloudUrl;
  final String clinicToken;

  @override
  bool operator ==(Object other) =>
      other is PairingPayload &&
      other.cloudUrl == cloudUrl &&
      other.clinicToken == clinicToken;

  @override
  int get hashCode => Object.hash(cloudUrl, clinicToken);

  @override
  String toString() => 'PairingPayload(cloudUrl: $cloudUrl, clinicToken: ***)';
}

/// The only pairing-payload version this app understands.
const int kPairingPayloadVersion = 1;

/// Parse a scanned QR string into a [PairingPayload].
///
/// Pure and side-effect free so it can be unit-tested without a camera. Returns
/// `null` on anything invalid:
///   * not JSON / not a JSON object
///   * wrong (or missing) version `v`
///   * missing or blank `u` (cloud url) or `t` (clinic token)
///   * a non-https url, unless it points at localhost / 127.0.0.1 (dev only)
PairingPayload? parsePairingPayload(String raw) {
  final trimmed = raw.trim();
  if (trimmed.isEmpty) return null;

  final Object? decoded;
  try {
    decoded = jsonDecode(trimmed);
  } on FormatException {
    return null;
  }
  if (decoded is! Map) return null;

  // Version must match exactly. Accept an int or its string form ("1"), but
  // reject anything else (missing, null, "2", etc.).
  final version = decoded['v'];
  final versionOk = version == kPairingPayloadVersion ||
      (version is String && int.tryParse(version) == kPairingPayloadVersion);
  if (!versionOk) return null;

  final url = (decoded['u'] is String) ? (decoded['u'] as String).trim() : '';
  final token = (decoded['t'] is String) ? (decoded['t'] as String).trim() : '';
  if (url.isEmpty || token.isEmpty) return null;

  if (!_isAcceptableUrl(url)) return null;

  return PairingPayload(cloudUrl: url, clinicToken: token);
}

/// https is required in the field; plain http is tolerated only for localhost so
/// developers can scan a QR from a desktop running on the same machine.
bool _isAcceptableUrl(String url) {
  final uri = Uri.tryParse(url);
  if (uri == null || !uri.hasScheme || uri.host.isEmpty) return false;
  if (uri.scheme == 'https') return true;
  if (uri.scheme == 'http') {
    final host = uri.host.toLowerCase();
    return host == 'localhost' || host == '127.0.0.1';
  }
  return false;
}
