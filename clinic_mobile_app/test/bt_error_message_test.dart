import 'dart:async';

import 'package:flutter_test/flutter_test.dart';

import 'package:clinic_mobile_app/utils/bt_error_message.dart';

void main() {
  group('btMessageFor — English', () {
    test('phoneBtOff', () {
      expect(btMessageFor(BtFailure.phoneBtOff, 'en'),
          'Turn on Bluetooth to sync.');
    });
    test('permissionDenied', () {
      expect(btMessageFor(BtFailure.permissionDenied, 'en'),
          'Allow Bluetooth permission in Android settings to sync.');
    });
    test('noPeerSelected', () {
      expect(btMessageFor(BtFailure.noPeerSelected, 'en'),
          'Choose your clinic PC first.');
    });
    test('notBonded', () {
      expect(btMessageFor(BtFailure.notBonded, 'en'),
          "Pair the clinic PC in your phone's Bluetooth settings first.");
    });
    test('peerUnreachable', () {
      expect(btMessageFor(BtFailure.peerUnreachable, 'en'),
          "Couldn't reach the clinic PC. Make sure it's on, nearby, and its Bluetooth is on.");
    });
    test('unknown', () {
      expect(btMessageFor(BtFailure.unknown, 'en'),
          'Bluetooth sync hit a problem. Please try again.');
    });
  });

  group('btMessageFor — Arabic', () {
    test('phoneBtOff (ar)', () {
      expect(btMessageFor(BtFailure.phoneBtOff, 'ar'),
          'قم بتشغيل البلوتوث للمزامنة.');
    });
    test('permissionDenied (ar)', () {
      expect(btMessageFor(BtFailure.permissionDenied, 'ar'),
          'يرجى السماح بإذن البلوتوث في إعدادات أندرويد للمزامنة.');
    });
    test('noPeerSelected (ar)', () {
      expect(btMessageFor(BtFailure.noPeerSelected, 'ar'),
          'اختر حاسوب العيادة أولاً.');
    });
    test('notBonded (ar)', () {
      expect(btMessageFor(BtFailure.notBonded, 'ar'),
          'قم بإقران حاسوب العيادة في إعدادات بلوتوث الهاتف أولاً.');
    });
    test('peerUnreachable (ar)', () {
      expect(btMessageFor(BtFailure.peerUnreachable, 'ar'),
          'تعذّر الوصول إلى حاسوب العيادة. تأكد من أنه قيد التشغيل وقريب والبلوتوث مفعّل.');
    });
    test('unknown (ar)', () {
      expect(btMessageFor(BtFailure.unknown, 'ar'),
          'حدثت مشكلة في مزامنة البلوتوث. يرجى المحاولة مرة أخرى.');
    });
  });

  group('classifyBtError', () {
    test('TimeoutException → peerUnreachable', () {
      expect(classifyBtError(TimeoutException('connect timed out')),
          BtFailure.peerUnreachable);
    });
    test('connect failed string → peerUnreachable', () {
      expect(classifyBtError(Exception('BT connect failed: PlatformException')),
          BtFailure.peerUnreachable);
    });
    test('read failed string → peerUnreachable', () {
      expect(classifyBtError(Exception('read failed, socket might closed')),
          BtFailure.peerUnreachable);
    });
    test('generic Exception → unknown', () {
      expect(classifyBtError(Exception('something else entirely')),
          BtFailure.unknown);
    });
    test('null/empty → unknown', () {
      expect(classifyBtError(''), BtFailure.unknown);
    });
  });
}
