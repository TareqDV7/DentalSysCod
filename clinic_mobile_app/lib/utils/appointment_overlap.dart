import '../models/appointment.dart';

/// Default slot length, in minutes, assumed when an appointment row has no
/// explicit duration recorded.
const int kDefaultAppointmentMinutes = 30;

/// Statuses that no longer hold their slot — a completed visit or a cancelled
/// booking does not block a new one. Everything else (scheduled, confirmed,
/// pending, postponed, …) counts as "taken" for conflict warnings.
const Set<String> _freeStatuses = {'completed', 'cancelled', 'canceled'};

/// True when two time ranges overlap: A starts before B ends AND B starts
/// before A ends. Back-to-back slots (one ends exactly as the next begins) do
/// NOT overlap. Mirrors the desktop server's conflict query
/// (dental_clinic.py:2781).
bool appointmentsOverlap(
  DateTime startA,
  int durationMinutesA,
  DateTime startB,
  int durationMinutesB,
) {
  final endA = startA.add(Duration(minutes: durationMinutesA));
  final endB = startB.add(Duration(minutes: durationMinutesB));
  return startA.isBefore(endB) && startB.isBefore(endA);
}

/// Existing appointments whose time range overlaps a proposed booking at
/// [start] lasting [durationMinutes]. Completed/cancelled rows and the row with
/// id [excludeId] (the appointment being edited, if any) are ignored. The
/// result is sorted by start time so the soonest clash is listed first.
List<Appointment> findAppointmentConflicts(
  Iterable<Appointment> existing,
  DateTime start,
  int durationMinutes, {
  int? excludeId,
}) {
  final conflicts = existing.where((a) {
    if (excludeId != null && a.id == excludeId) return false;
    if (_freeStatuses.contains(a.status.toLowerCase())) return false;
    return appointmentsOverlap(
      start,
      durationMinutes,
      a.dateTime,
      a.durationMinutes ?? kDefaultAppointmentMinutes,
    );
  }).toList()
    ..sort((x, y) => x.dateTime.compareTo(y.dateTime));
  return conflicts;
}
