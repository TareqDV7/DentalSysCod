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
  static const _cloudUrlKey = 'cloud_url';
  static const _cloudClinicTokenKey = 'cloud_clinic_token';
  static const _cloudClinicIdKey = 'cloud_clinic_id';
  static const _btEnabledKey = 'bt_enabled';
  static const _btBondedMacKey = 'bt_bonded_mac';
  static const _btBondedLabelKey = 'bt_bonded_label';
  static const _btLastSyncAtKey = 'bt_last_sync_at';
  static const _btLastErrorKey = 'bt_last_error';
  static const _doctorNameEnKey = 'doctor_name_en';
  static const _doctorNameArKey = 'doctor_name_ar';
  static const _doctorNamePendingKey = 'doctor_name_pending_push';
  static const _licenseExpiryKey = 'license_expires_at';

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

  // ── Clinic profile (doctor name) ──────────────────────────────────────────
  Future<void> setDoctorNameEn(String value) =>
      _storage.write(key: _doctorNameEnKey, value: value);

  Future<String?> getDoctorNameEn() => _storage.read(key: _doctorNameEnKey);

  Future<void> setDoctorNameAr(String value) =>
      _storage.write(key: _doctorNameArKey, value: value);

  Future<String?> getDoctorNameAr() => _storage.read(key: _doctorNameArKey);

  /// Whether a local doctor-name edit hasn't reached the server yet, so the
  /// next online refresh re-pushes it instead of pulling a stale value over it.
  Future<void> setDoctorNamePending(bool pending) =>
      _storage.write(key: _doctorNamePendingKey, value: pending ? '1' : '0');

  Future<bool> getDoctorNamePending() async =>
      (await _storage.read(key: _doctorNamePendingKey)) == '1';

  Future<void> setSerialNumber(String value) =>
      _storage.write(key: _serialNumberKey, value: value);

  Future<String?> getSerialNumber() => _storage.read(key: _serialNumberKey);

  Future<void> setLicenseExpiry(String value) =>
      _storage.write(key: _licenseExpiryKey, value: value);

  Future<String?> getLicenseExpiry() => _storage.read(key: _licenseExpiryKey);

  Future<void> setClinicName(String value) =>
      _storage.write(key: _clinicNameKey, value: value);

  Future<String?> getClinicName() => _storage.read(key: _clinicNameKey);

  // ── Cloud account (links this device to a clinic on the shared cloud node) ──

  Future<void> setCloudAccount({
    required String cloudUrl,
    required String clinicToken,
    int? clinicId,
  }) async {
    await _storage.write(key: _cloudUrlKey, value: cloudUrl);
    await _storage.write(key: _cloudClinicTokenKey, value: clinicToken);
    if (clinicId != null) {
      await _storage.write(key: _cloudClinicIdKey, value: clinicId.toString());
    }
  }

  Future<void> clearCloudAccount() async {
    await _storage.delete(key: _cloudUrlKey);
    await _storage.delete(key: _cloudClinicTokenKey);
    await _storage.delete(key: _cloudClinicIdKey);
  }

  Future<String?> getCloudUrl() => _storage.read(key: _cloudUrlKey);

  Future<String?> getCloudClinicToken() =>
      _storage.read(key: _cloudClinicTokenKey);

  Future<int?> getCloudClinicId() async {
    final v = await _storage.read(key: _cloudClinicIdKey);
    return v == null ? null : int.tryParse(v);
  }

  // ── Bluetooth peer (links this device to a clinic PC over BT-SPP) ──

  Future<bool> getBtEnabled() async {
    final v = await _storage.read(key: _btEnabledKey);
    return v == '1';
  }

  Future<void> setBtEnabled(bool enabled) =>
      _storage.write(key: _btEnabledKey, value: enabled ? '1' : '0');

  Future<String?> getBtBondedMac() => _storage.read(key: _btBondedMacKey);

  Future<String?> getBtBondedLabel() => _storage.read(key: _btBondedLabelKey);

  Future<void> setBtBondedPeer({required String mac, required String label}) async {
    await _storage.write(key: _btBondedMacKey, value: mac);
    await _storage.write(key: _btBondedLabelKey, value: label);
  }

  Future<void> clearBtBondedPeer() async {
    await _storage.delete(key: _btBondedMacKey);
    await _storage.delete(key: _btBondedLabelKey);
  }

  Future<String?> getBtLastSyncAt() => _storage.read(key: _btLastSyncAtKey);

  Future<void> setBtLastSyncAt(String iso) =>
      _storage.write(key: _btLastSyncAtKey, value: iso);

  Future<String?> getBtLastError() => _storage.read(key: _btLastErrorKey);

  Future<void> setBtLastError(String message) =>
      _storage.write(key: _btLastErrorKey, value: message);

  Future<void> clearBtLastError() => _storage.delete(key: _btLastErrorKey);
}
