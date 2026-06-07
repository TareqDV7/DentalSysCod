/// Resolve the display name for a patient reference.
///
/// Rows the desktop exports over sync (appointments, visits, billing) carry
/// only `patient_id`. The desktop resolves `patient_name` with a SQL JOIN at
/// read time and never stores it on the row, so the column arrives `null` on
/// the phone — which is why a synced appointment used to render as
/// "Patient #4". This mirrors that JOIN locally: prefer a non-blank stored
/// name, otherwise build it from the joined patient's first/last name.
///
/// Returns `null` only when neither source yields a usable name, leaving the
/// caller to fall back to a "Patient #id" placeholder.
String? resolvePatientName(String? stored, {String? firstName, String? lastName}) {
  final s = stored?.trim();
  if (s != null && s.isNotEmpty && s.toLowerCase() != 'null') return s;
  final full = '${firstName?.trim() ?? ''} ${lastName?.trim() ?? ''}'.trim();
  return full.isEmpty ? null : full;
}