import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:uuid/uuid.dart';

class LocalStorageService {
  static const _storage = FlutterSecureStorage();
  static const _deviceIdKey = 'device_id';
  static const _deviceTokenKey = 'device_token';
  static const _baseUrlKey = 'base_url';
  static const _onlineUrlKey = 'online_url';
  static const _localUrlKey = 'local_url';
  static const _lastSuccessfulUrlKey = 'last_successful_url';
  static const _serialNumberKey = 'serial_number';
  static const _clinicNameKey = 'clinic_name';

  Future<String> getOrCreateDeviceId() async {
    final existing = await _storage.read(key: _deviceIdKey);
    if (existing != null && existing.isNotEmpty) {
      return existing;
    }
    const uuid = Uuid();
    final generated = uuid.v4();
    await _storage.write(key: _deviceIdKey, value: generated);
    return generated;
  }

  Future<void> setDeviceToken(String token) =>
      _storage.write(key: _deviceTokenKey, value: token);

  Future<String?> getDeviceToken() => _storage.read(key: _deviceTokenKey);

  Future<void> setBaseUrl(String value) =>
      _storage.write(key: _baseUrlKey, value: value);

  Future<String?> getBaseUrl() => _storage.read(key: _baseUrlKey);

  Future<void> setOnlineUrl(String value) =>
      _storage.write(key: _onlineUrlKey, value: value);

  Future<String?> getOnlineUrl() async {
    final value = await _storage.read(key: _onlineUrlKey);
    if (value != null && value.isNotEmpty) {
      return value;
    }
    return _storage.read(key: _baseUrlKey);
  }

  Future<void> setLocalUrl(String value) =>
      _storage.write(key: _localUrlKey, value: value);

  Future<String?> getLocalUrl() async {
    final value = await _storage.read(key: _localUrlKey);
    if (value != null && value.isNotEmpty) {
      return value;
    }
    return _storage.read(key: _baseUrlKey);
  }

  Future<void> setLastSuccessfulUrl(String value) =>
      _storage.write(key: _lastSuccessfulUrlKey, value: value);

  Future<String?> getLastSuccessfulUrl() async {
    final value = await _storage.read(key: _lastSuccessfulUrlKey);
    if (value != null && value.isNotEmpty) {
      return value;
    }
    return _storage.read(key: _baseUrlKey);
  }

  Future<void> setSerialNumber(String value) =>
      _storage.write(key: _serialNumberKey, value: value);

  Future<String?> getSerialNumber() => _storage.read(key: _serialNumberKey);

  Future<void> setClinicName(String value) =>
      _storage.write(key: _clinicNameKey, value: value);

  Future<String?> getClinicName() => _storage.read(key: _clinicNameKey);
}
