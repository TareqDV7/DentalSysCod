import 'dart:async';

import 'package:flutter/material.dart';
import '../services/clinic_api.dart';
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
  late final PatientService patients;
  late final AppointmentService appointments;
  late final BillingService billing;
  late final ReportService reports;
  late final ConnectivitySyncService sync;

  String _clinicName = 'Clinic';
  String _locale = 'en';
  ThemeMode _themeMode = ThemeMode.light;

  AppState(this._storage) {
    db = DatabaseService.instance;
    api = ClinicApi();
    patients = PatientService(db, api);
    appointments = AppointmentService(db, api);
    billing = BillingService(db, api);
    reports = ReportService(db, api);
    final internet = InternetSyncService(db, api);
    final bluetooth = BluetoothSyncService(db);
    sync = ConnectivitySyncService(internet, bluetooth);
  }

  String get clinicName => _clinicName;
  String get locale => _locale;
  ThemeMode get themeMode => _themeMode;
  bool get isArabic => _locale == 'ar';

  Future<void> init() async {
    final baseUrl = await _storage.getBaseUrl();
    final token = await _storage.getDeviceToken();
    final clinic = await _storage.getClinicName();
    if (baseUrl != null) api.baseUrl = baseUrl;
    if (token != null) api.deviceToken = token;
    if (clinic != null) _clinicName = clinic;
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
    notifyListeners();
  }

  @override
  void dispose() {
    sync.dispose();
    super.dispose();
  }
}
