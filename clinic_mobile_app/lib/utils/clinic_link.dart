/// Decide whether re-linking this device to [newClinicId] means it is joining a
/// DIFFERENT clinic than [previousClinicId].
///
/// When true, the caller must discard this device's local records before syncing:
/// they belong to the old clinic, and because rows sync by primary `id` with
/// last-write-wins, leftover rows would otherwise linger on the device or even
/// collide with — and overwrite — a real record on the newly-linked clinic.
///
/// Returns false for a first-time link (no previous clinic) and for re-linking to
/// the same clinic, so neither path is disrupted. Also returns false when the new
/// clinic id is unknown — we never take a destructive action we can't justify.
bool clinicSwitchRequiresLocalReset({
  required int? previousClinicId,
  required int? newClinicId,
}) {
  if (previousClinicId == null || newClinicId == null) return false;
  return previousClinicId != newClinicId;
}
