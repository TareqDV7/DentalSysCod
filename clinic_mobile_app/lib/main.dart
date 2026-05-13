import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'theme/clinic_brand.dart';
import 'state/app_state.dart';
import 'screens/home_screen.dart';
import 'screens/settings_screen.dart';
import 'services/local_storage_service.dart';

void main() {
  runApp(const ClinicMobileApp());
}

class ClinicMobileApp extends StatefulWidget {
  const ClinicMobileApp({super.key});

  @override
  State<ClinicMobileApp> createState() => _ClinicMobileAppState();
}

class _ClinicMobileAppState extends State<ClinicMobileApp> {
  final _storage = LocalStorageService();
  late final AppState _appState;

  @override
  void initState() {
    super.initState();
    _appState = AppState(_storage);
  }

  @override
  void dispose() {
    _appState.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider.value(
      value: _appState,
      child: Consumer<AppState>(
        builder: (_, state, _) => MaterialApp(
          title: 'Dental Clinic',
          debugShowCheckedModeBanner: false,
          theme: ClinicBrand.buildTheme(dark: false),
          darkTheme: ClinicBrand.buildTheme(dark: true),
          themeMode: state.themeMode,
          home: const AppEntry(),
          routes: {
            '/settings': (_) => const SettingsScreen(),
          },
        ),
      ),
    );
  }
}

class AppEntry extends StatefulWidget {
  const AppEntry({super.key});

  @override
  State<AppEntry> createState() => _AppEntryState();
}

class _AppEntryState extends State<AppEntry> {
  bool _ready = false;

  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    await context.read<AppState>().init();
    if (!mounted) return;
    setState(() => _ready = true);
  }

  @override
  Widget build(BuildContext context) {
    if (!_ready) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    return const HomeScreen();
  }
}
