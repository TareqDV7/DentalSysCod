/// Pick the doctor name to display for the current [locale], falling back to
/// the other language when the preferred one is blank. Keeps the header and
/// printed materials reading naturally in either language.
String resolveDoctorName(String en, String ar, String locale) {
  final e = en.trim();
  final a = ar.trim();
  if (locale == 'ar') return a.isNotEmpty ? a : e;
  return e.isNotEmpty ? e : a;
}
