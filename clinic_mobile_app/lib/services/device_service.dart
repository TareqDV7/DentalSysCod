import 'dart:convert';
import 'dart:io';

import 'package:device_info_plus/device_info_plus.dart';
import 'local_storage_service.dart';

class DeviceService {
  final _storage = LocalStorageService();
  final _deviceInfo = DeviceInfoPlugin();

  /// Returns a hardware-based device id when possible, otherwise falls back
  /// to a persisted UUID.
  Future<String> getDeviceId() async {
    // If already stored, return it (ensures stability)
    final existing = await _storage.getOrCreateDeviceId();
    try {
      if (Platform.isAndroid || Platform.isIOS) {
        final info = await _deviceInfo.deviceInfo;
        final map = info.data;
        // Try common hardware identifiers
        if (map.containsKey('id') && map['id'] != null) {
          final id = map['id'].toString();
          final hw = 'DEVICE-${_normalize(id)}';
          return hw;
        }
        if (map.containsKey('id') == false && map.containsKey('identifierForVendor')) {
          final id = map['identifierForVendor'] ?? map['identifier_for_vendor'];
          if (id != null) {
            final hw = 'DEVICE-${_normalize(id.toString())}';
            return hw;
          }
        }
      }

      if (Platform.isWindows) {
        // Use WMIC to get baseboard serial
        final result = await Process.run('wmic', ['baseboard', 'get', 'serialnumber']);
        final out = result.stdout.toString().split('\n');
        if (out.length > 1) {
          final serial = out[1].trim();
          if (serial.isNotEmpty) return 'DEVICE-${_normalize(serial)}';
        }
      }

      if (Platform.isMacOS) {
        final result = await Process.run('ioreg', ['-rd1', '-c', 'IOPlatformExpertDevice']);
        final out = result.stdout.toString();
        final match = RegExp(r'"IOPlatformSerialNumber" = "([^"]+)"').firstMatch(out);
        if (match != null) return 'DEVICE-${_normalize(match.group(1)!)}';
      }

      if (Platform.isLinux) {
        final result = await Process.run('cat', ['/etc/machine-id']);
        final id = result.stdout.toString().trim();
        if (id.isNotEmpty) return 'DEVICE-${_normalize(id)}';
      }
    } catch (_) {
      // Fall back to stored/generated ID
    }

    // Fallback: use persisted UUID
    final fallback = existing;
    return 'DEVICE-${_normalize(fallback)}';
  }

  String _normalize(String v) {
    return base64Url.encode(utf8.encode(v)).replaceAll('=', '').toUpperCase().substring(0, 16);
  }
}
