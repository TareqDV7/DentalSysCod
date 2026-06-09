import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../config/app_config.dart';
import '../services/license_gate_service.dart';
import '../state/app_state.dart';
import '../utils/app_strings.dart';
import '../widgets/sync_status_bar.dart';
import '../widgets/brand_logo.dart';
import 'dashboard_screen.dart';
import 'patients_screen.dart';
import 'appointments_screen.dart';
import 'financial_screen.dart';
import 'reports_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _index = 0;
  LicenseGateState _gate = const GateUnknown();
  bool _graceDismissed = false;

  static final _screens = [
    const DashboardScreen(),
    const PatientsScreen(),
    const AppointmentsScreen(),
    const FinancialScreen(),
    const ReportsScreen(),
  ];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _checkGate());
  }

  Future<void> _checkGate() async {
    if (!mounted) return;
    final api = context.read<AppState>().api;
    final baseUrl = api.baseUrl;
    if (baseUrl.isEmpty) return;
    final gate = await LicenseGateService().fetchGate(
      baseUrl: baseUrl,
      deviceToken: api.deviceToken,
    );
    if (!mounted) return;
    setState(() => _gate = gate);
  }

  Widget _buildLicenseBanner() {
    final ar = context.read<AppState>().isArabic;
    return switch (_gate) {
      GateGrace(:final graceUntil) when !_graceDismissed => MaterialBanner(
        content: Text(
            '${AppStrings.t('renew_by_prefix', isArabic: ar)}$graceUntil'),
        backgroundColor: Colors.amber.shade100,
        actions: [
          TextButton(
            onPressed: () => setState(() => _graceDismissed = true),
            child: Text(AppStrings.t('dismiss', isArabic: ar)),
          ),
        ],
      ),
      GateViewOnly() => MaterialBanner(
        content: Text(AppStrings.t('view_only_renew', isArabic: ar)),
        backgroundColor: Colors.red.shade100,
        actions: const [SizedBox.shrink()],
      ),
      _ => const SizedBox.shrink(),
    };
  }

  Widget _buildUnlicensedBlock() {
    final ar = context.read<AppState>().isArabic;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // "Outside" brand identity on the entry/gate screen.
            const BrandLogo(size: 76, radius: 20),
            const SizedBox(height: 16),
            Text(
              AppBranding.systemName,
              style: const TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.w800,
                  letterSpacing: -0.3),
            ),
            const SizedBox(height: 24),
            const Icon(Icons.lock_outline, size: 48, color: Colors.grey),
            const SizedBox(height: 12),
            Text(
              AppStrings.t('activate_on_desktop_title', isArabic: ar),
              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 8),
            Text(
              AppStrings.t('activate_on_desktop_body', isArabic: ar),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            // Brand logo mark (the real app icon, not a generic glyph)
            const BrandLogo(size: 34, radius: 10),
            const SizedBox(width: 10),
            // System name + clinic name stacked
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    AppBranding.systemName,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w800,
                      letterSpacing: -0.3,
                      height: 1.1,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                  Text(
                    state.clinicName.isNotEmpty
                        ? state.clinicName
                        : AppBranding.clinicName,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: scheme.onSurfaceVariant,
                      fontWeight: FontWeight.w500,
                      height: 1.1,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            icon: Icon(
              state.themeMode == ThemeMode.dark
                  ? Icons.light_mode_outlined
                  : Icons.dark_mode_outlined,
            ),
            tooltip: state.themeMode == ThemeMode.dark
                ? AppStrings.t('switch_to_light', isArabic: state.isArabic)
                : AppStrings.t('switch_to_dark', isArabic: state.isArabic),
            onPressed: () => state.setThemeMode(
              state.themeMode == ThemeMode.dark
                  ? ThemeMode.light
                  : ThemeMode.dark,
            ),
          ),
          IconButton(
            icon: const Icon(Icons.settings_outlined),
            tooltip: AppStrings.t('settings', isArabic: state.isArabic),
            onPressed: () => Navigator.pushNamed(context, '/settings'),
          ),
        ],
      ),
      body: Column(
        children: [
          _buildLicenseBanner(),
          const SyncStatusBar(),
          Expanded(
            child: switch (_gate) {
              GateUnlicensed() => _buildUnlicensedBlock(),
              GateActive() ||
              GateGrace() ||
              GateViewOnly() ||
              GateUnknown() =>
                IndexedStack(index: _index, children: _screens),
            },
          ),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) {
          setState(() => _index = i);
          // Re-opening the kept-alive Dashboard: nudge it to reload so stats
          // reflect edits just made on the Financial / Patients / Appointments
          // tabs (e.g. a billing receipt) instead of a stale cached value.
          if (i == 0) context.read<AppState>().pingDashboard();
        },
        destinations: [
          NavigationDestination(
            icon: const Icon(Icons.dashboard_outlined),
            selectedIcon: const Icon(Icons.dashboard),
            label: AppStrings.t('nav_dashboard', isArabic: state.isArabic),
          ),
          NavigationDestination(
            icon: const Icon(Icons.people_outline),
            selectedIcon: const Icon(Icons.people),
            label: AppStrings.t('nav_patients', isArabic: state.isArabic),
          ),
          NavigationDestination(
            icon: const Icon(Icons.calendar_month_outlined),
            selectedIcon: const Icon(Icons.calendar_month),
            label: AppStrings.t('appointments', isArabic: state.isArabic),
          ),
          NavigationDestination(
            icon: const Icon(Icons.account_balance_wallet_outlined),
            selectedIcon: const Icon(Icons.account_balance_wallet),
            label: AppStrings.t('nav_financial', isArabic: state.isArabic),
          ),
          NavigationDestination(
            icon: const Icon(Icons.bar_chart_outlined),
            selectedIcon: const Icon(Icons.bar_chart),
            label: AppStrings.t('nav_reports', isArabic: state.isArabic),
          ),
        ],
      ),
    );
  }
}
