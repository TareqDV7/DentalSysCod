/// Mask a license serial for display, revealing only the last four characters
/// (e.g. `DENTAL-ABCD-1234` → `••••1234`). Short serials are shown unmasked.
String maskSerial(String serial) {
  final s = serial.trim();
  if (s.length <= 4) return s;
  return '••••${s.substring(s.length - 4)}';
}

/// The calendar date (`YYYY-MM-DD`) a license is valid until, taken from the
/// ISO timestamp embedded in the activation key. Returns null when the value is
/// missing or isn't a well-formed date, so the UI can simply omit the line.
String? licenseExpiryDate(String? iso) {
  final v = (iso ?? '').trim();
  if (v.length < 10) return null;
  final date = v.substring(0, 10);
  return RegExp(r'^\d{4}-\d{2}-\d{2}$').hasMatch(date) ? date : null;
}
