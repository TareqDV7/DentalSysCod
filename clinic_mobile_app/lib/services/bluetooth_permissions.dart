import 'package:permission_handler/permission_handler.dart';

/// Runtime gate for the Android-12+ Bluetooth permissions. The manifest
/// declares them, but `BLUETOOTH_CONNECT` / `BLUETOOTH_SCAN` are runtime-grant
/// since API 31 — without an explicit request, `flutter_bluetooth_serial`
/// silently returns empty bond lists and connect calls throw a generic
/// PlatformException, which looks to the user like "Bluetooth just doesn't
/// work." On Android 11 and below these are install-time and the helpers
/// here resolve to granted no-ops.
class BluetoothPermissions {
  /// Prompts the user (if not already granted). MUST be called from a
  /// foreground activity context.
  static Future<bool> ensureGranted() async {
    final results = await [
      Permission.bluetoothConnect,
      Permission.bluetoothScan,
    ].request();
    return results.values.every((s) => s.isGranted);
  }

  /// Non-prompting check — safe to call from anywhere. Returns false if
  /// either permission is missing or permanently denied.
  static Future<bool> areGranted() async {
    final connect = await Permission.bluetoothConnect.status;
    final scan = await Permission.bluetoothScan.status;
    return connect.isGranted && scan.isGranted;
  }
}
