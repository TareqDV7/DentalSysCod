import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/utils/clinic_link.dart';

void main() {
  group('clinicSwitchRequiresLocalReset', () {
    test('true when re-linking to a different clinic', () {
      // The bug: a phone previously linked to clinic 7 pastes the desktop's key
      // (clinic 16). Its stale cursor + already-synced flags mean nothing crosses
      // and the banner falsely reads "Synced". The caller must wipe local data so
      // the new clinic mirrors cleanly.
      expect(
        clinicSwitchRequiresLocalReset(previousClinicId: 7, newClinicId: 16),
        isTrue,
      );
    });

    test('false on a first-time link (no previous clinic)', () {
      // Fresh install: empty DB + null cursor already do a full pull; wiping
      // would be pointless and a same-key first link must not be disrupted.
      expect(
        clinicSwitchRequiresLocalReset(previousClinicId: null, newClinicId: 16),
        isFalse,
      );
    });

    test('false when re-linking to the SAME clinic', () {
      // License refresh / re-entering the same key: keep steady-state sync; never
      // wipe a working device's data.
      expect(
        clinicSwitchRequiresLocalReset(previousClinicId: 16, newClinicId: 16),
        isFalse,
      );
    });

    test('false when the new clinic id is unknown (cannot prove a switch)', () {
      // Don't take a destructive action we can't justify.
      expect(
        clinicSwitchRequiresLocalReset(previousClinicId: 16, newClinicId: null),
        isFalse,
      );
    });

    test('false when both ids are unknown', () {
      expect(
        clinicSwitchRequiresLocalReset(previousClinicId: null, newClinicId: null),
        isFalse,
      );
    });
  });
}
