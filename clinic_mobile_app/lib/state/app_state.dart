import 'dart:async';

import 'package:flutter/material.dart';
import '../services/clinic_api.dart';
import '../services/cloud_sync_service.dart';
import '../services/database_service.dart';
import '../services/patient_service.dart';
import '../services/appointment_service.dart';
import '../services/billing_service.dart';
import '../services/report_service.dart';
import '../services/internet_sync_service.dart';
import '../services/bluetooth_sync_service.dart';
import '../services/connectivity_sync_service.dart';
import '../services/local_storage_service.dart';

class AppState extends ChangeNotifier {
  final LocalStorageService _storage;

  late final ClinicApi api;
  late final DatabaseService db;
  late final CloudSyncService cloud;
  late final PatientService patients;
  late final AppointmentService appointments;
  late final BillingService billing;
  late final ReportService reports;
  late final ConnectivitySyncService sync;

  String _clinicName = 'Clinic';
  String _locale = 'en';
  ThemeMode _themeMode = ThemeMode.light;
  String? _cloudUrl;
  bool _hasCloudAccount = false;

  AppState(this._storage) {
    db = DatabaseService.instance;
    api = ClinicApi();
    cloud = CloudSyncService();
    patients = PatientService(db, api);
    appointments = AppointmentService(db, api);
    billing = BillingService(db, api);
    reports = ReportService(db, api);
    final internet = InternetSyncService(db, api);
    final bluetooth = BluetoothSyncService(db);
    sync = ConnectivitySyncService(
      internet: internet,
      bluetooth: bluetooth,
      storage: _storage,
      api: api,
      cloud: cloud,
    );
  }

  String get clinicName => _clinicName;
  String get locale => _locale;
  ThemeMode get themeMode => _themeMode;
  bool get isArabic => _locale == 'ar';
  String? get cloudUrl => _cloudUrl;
  bool get hasCloudAccount => _hasCloudAccount;

  Future<void> init() async {
    final baseUrl = await _storage.getBaseUrl();
    final token = await _storage.getDeviceToken();
    final clinic = await _storage.getClinicName();
    final cloudUrl = await _storage.getCloudUrl();
    final clinicToken = await _storage.getCloudClinicToken();
    if (baseUrl != null) api.baseUrl = baseUrl;
    if (token != null) api.deviceToken = token;
    if (clinicToken != null) api.clinicToken = clinicToken;
    if (clinic != null) _clinicName = clinic;
    _cloudUrl = cloudUrl;
    _hasCloudAccount = (cloudUrl != null && cloudUrl.isNotEmpty) &&
        (clinicToken != null && clinicToken.isNotEmpty);
    notifyListeners();
    unawaited(sync.syncNow().catchError((error) {
      debugPrint('Initial sync failed: $error');
    }));
  }

  void setLocale(String locale) {
    _locale = locale;
    notifyListeners();
  }

  void setThemeMode(ThemeMode mode) {
    _themeMode = mode;
    notifyListeners();
  }

  Future<void> updateServerUrl(String url) async {
    api.baseUrl = url;
    await _storage.setBaseUrl(url);
    await _storage.setLocalUrl(url);
    notifyListeners();
  }

  /// Register this device's clinic on the shared cloud node and remember the token
  /// so subsequent syncs can fall back to (or run against) the cloud.
  Future<CloudAccountInfo> pairCloud({
    required String cloudUrl,
    required String serialNumber,
    required String clinicName,
  }) async {
    final info = await cloud.register(
      cloudUrl: cloudUrl,
      serialNumber: serialNumber,
      clinicName: clinicName,
    );
    await _storage.setCloudAccount(
      cloudUrl: cloudUrl,
      clinicToken: info.clinicToken,
      clinicId: info.clinicId,
    );
    if (clinicName.trim().isNotEmpty) {
      await _storage.setClinicName(clinicName.trim());
      _clinicName = clinicName.trim();
    }
    _cloudUrl = cloudUrl;
    _hasCloudAccount = true;
    api.clinicToken = info.clinicToken;
    notifyListeners();
    // Try a sync right away against the new target.
    unawaited(sync.syncNow());
    return info;
  }

  Future<void> unpairCloud() async {
    await _storage.clearCloudAccount();
    api.clinicToken = null;
    _cloudUrl = null;
    _hasCloudAccount = false;
    notifyListeners();
  }

  @override
  void dispose() {
    sync.dispose();
    super.dispose();
  }
}
