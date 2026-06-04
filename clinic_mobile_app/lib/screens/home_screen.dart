import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../config/app_config.dart';
import '../services/license_gate_service.dart';
import '../state/app_state.dart';
import '../widgets/sync_status_bar.dart';
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
    return switch (_gate) {
      GateGrace(:final graceUntil) when !_graceDismissed => MaterialBanner(
        content: Text('Renew on the clinic desktop by $graceUntil'),
        backgroundColor: Colors.amber.shade100,
        actions: [
          TextButton(
            onPressed: () => setState(() => _graceDismissed = true),
            child: const Text('Dismiss'),
          ),
        ],
      ),
      GateViewOnly() => MaterialBanner(
        content: const Text('View only — ask the clinic to renew'),
        backgroundColor: Colors.red.shade100,
        actions: const [SizedBox.shrink()],
      ),
      _ => const SizedBox.shrink(),
    };
  }

  Widget _buildUnlicensedBlock() {
    return const Center(
      child: Padding(
        padding: EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.lock_outline, size: 64, color: Colors.grey),
            SizedBox(height: 16),
            Text(
              'Activate on the desktop first',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
              textAlign: TextAlign.center,
            ),
            SizedBox(height: 8),
            Text(
              'Open the dental clinic desktop app and complete activation.',
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
            // Logo mark
            Container(
              width: 34,
              height: 34,
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  colors: [Color(0xFF0F6D7B), Color(0xFF1D7FB7)],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                borderRadius: BorderRadius.circular(10),
              ),
              child: const Icon(
                Icons.local_hospital,
                color: Colors.white,
                size: 18,
              ),
            ),
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
                ? 'Switch to light mode'
                : 'Switch to dark mode',
            onPressed: () => state.setThemeMode(
              state.themeMode == ThemeMode.dark
                  ? ThemeMode.light
                  : ThemeMode.dark,
            ),
          ),
          IconButton(
            icon: const Icon(Icons.settings_outlined),
            tooltip: 'Settings',
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
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.dashboard_outlined),
            selectedIcon: Icon(Icons.dashboard),
            label: 'Dashboard',
          ),
          NavigationDestination(
            icon: Icon(Icons.people_outline),
            selectedIcon: Icon(Icons.people),
            label: 'Patients',
          ),
          NavigationDestination(
            icon: Icon(Icons.calendar_month_outlined),
            selectedIcon: Icon(Icons.calendar_month),
            label: 'Appointments',
          ),
          NavigationDestination(
            icon: Icon(Icons.account_balance_wallet_outlined),
            selectedIcon: Icon(Icons.account_balance_wallet),
            label: 'Financial',
          ),
          NavigationDestination(
            icon: Icon(Icons.bar_chart_outlined),
            selectedIcon: Icon(Icons.bar_chart),
            label: 'Reports',
          ),
        ],
      ),
    );
  }
}
