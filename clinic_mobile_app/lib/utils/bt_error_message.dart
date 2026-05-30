import 'dart:async';

/// Classified Bluetooth-sync failure. The caller picks the concrete enum
/// value based on what it knows (BT on/off, permission, peer chosen, etc.).
/// The one catch-all — `peerUnreachable` — covers everything classic BT
/// can't distinguish from the phone side (PC's BT off, PC asleep, app
/// closed, out of range).
enum BtFailure {
  phoneBtOff,
  permissionDenied,
  noPeerSelected,
  notBonded,
  peerUnreachable,
  unknown,
}

/// Map a thrown exception/error from the BT connection or session path to a
/// [BtFailure]. Used in catch blocks where the caller doesn't already know
/// the failure category. Heuristic — checks for the well-known strings the
/// flutter_bluetooth_serial layer surfaces; everything else → unknown.
BtFailure classifyBtError(Object error) {
  if (error is TimeoutException) return BtFailure.peerUnreachable;
  final s = error.toString().toLowerCase();
  if (s.contains('connect failed') ||
      s.contains('read failed') ||
      s.contains('socket might closed') ||
      s.contains('connection refused') ||
      s.contains('host is down') ||
      s.contains('no route')) {
    return BtFailure.peerUnreachable;
  }
  return BtFailure.unknown;
}

/// Plain-language message for a given failure, in the caller's locale.
/// [locale] follows the app's `'en'` / `'ar'` convention used elsewhere
/// (anything other than `'ar'` is treated as English).
String btMessageFor(BtFailure kind, String locale) {
  final ar = locale == 'ar';
  switch (kind) {
    case BtFailure.phoneBtOff:
      return ar
          ? 'قم بتشغيل البلوتوث للمزامنة.'
          : 'Turn on Bluetooth to sync.';
    case BtFailure.permissionDenied:
      return ar
          ? 'يرجى السماح بإذن البلوتوث في إعدادات أندرويد للمزامنة.'
          : 'Allow Bluetooth permission in Android settings to sync.';
    case BtFailure.noPeerSelected:
      return ar
          ? 'اختر حاسوب العيادة أولاً.'
          : 'Choose your clinic PC first.';
    case BtFailure.notBonded:
      return ar
          ? 'قم بإقران حاسوب العيادة في إعدادات بلوتوث الهاتف أولاً.'
          : "Pair the clinic PC in your phone's Bluetooth settings first.";
    case BtFailure.peerUnreachable:
      return ar
          ? 'تعذّر الوصول إلى حاسوب العيادة. تأكد من أنه قيد التشغيل وقريب والبلوتوث مفعّل.'
          : "Couldn't reach the clinic PC. Make sure it's on, nearby, and its Bluetooth is on.";
    case BtFailure.unknown:
      return ar
          ? 'حدثت مشكلة في مزامنة البلوتوث. يرجى المحاولة مرة أخرى.'
          : 'Bluetooth sync hit a problem. Please try again.';
  }
}
