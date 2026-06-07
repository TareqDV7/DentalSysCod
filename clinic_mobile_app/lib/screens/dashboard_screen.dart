import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';
import '../state/app_state.dart';
import '../models/appointment.dart';
import '../services/connectivity_sync_service.dart';
import '../widgets/stat_card.dart';
import '../widgets/section_header.dart';
import '../widgets/status_badge.dart';
import '../widgets/empty_state.dart';
import '../widgets/clinic_card.dart';
import '../utils/app_strings.dart';
import '../utils/date_format_helper.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  static final _money = NumberFormat('#,##0');

  Map<String, dynamic> _stats = {};
  Map<String, List<double>> _trends = {};
  List<Appointment> _recent = [];
  bool _loading = true;
  StreamSubscription<SyncStatus>? _syncSub;

  @override
  void initState() {
    super.initState();
    _load();
    // Kept alive in the home IndexedStack, so initState runs once. Refresh the
    // stats + recent appointments whenever a background sync completes.
    _syncSub = context.read<AppState>().sync.statusStream.listen((status) {
      if (status == SyncStatus.synced && mounted) _load(silent: true);
    });
  }

  @override
  void dispose() {
    _syncSub?.cancel();
    super.dispose();
  }

  Future<void> _load({bool silent = false}) async {
    if (!silent) setState(() => _loading = true);
    final state = context.read<AppState>();
    final stats = await state.db.getStats();
    final trends = await state.db.getDashboardTrends();
    final recent = await state.appointments.getRecentAppointments(limit: 10);
    if (mounted) {
      setState(() {
        _stats = stats;
        _trends = trends;
        _recent = recent;
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final isArabic = context.watch<AppState>().isArabic;

    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
        children: [
          // ── Stats grid (4 cards, 2-per-row) ──────────────────────────
          GridView.count(
            crossAxisCount: 2,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            crossAxisSpacing: 12,
            mainAxisSpacing: 12,
            childAspectRatio: 0.9,
            children: [
              StatCard(
                label: AppStrings.t('total_patients', isArabic: isArabic),
                value: '${_stats['total_patients'] ?? 0}',
                icon: Icons.people_alt_outlined,
                color: const Color(0xFF0F6D7B),
                trend: _trends['patients'],
              ),
              StatCard(
                label: AppStrings.t('todays_appointments', isArabic: isArabic),
                value: '${_stats['today_appointments'] ?? 0}',
                icon: Icons.event_outlined,
                color: const Color(0xFF1D7FB7),
                trend: _trends['appointments'],
              ),
              StatCard(
                label: AppStrings.t('total_visits', isArabic: isArabic),
                value: '${_stats['total_visits'] ?? 0}',
                icon: Icons.medical_services_outlined,
                color: const Color(0xFF1F9A5F),
                trend: _trends['visits'],
              ),
              StatCard(
                label: AppStrings.t('revenue', isArabic: isArabic),
                value: '₪ ${_money.format((_stats['total_revenue'] as num?) ?? 0)}',
                icon: Icons.payments_outlined,
                color: const Color(0xFFC47F10),
                trend: _trends['revenue'],
                trendLabelFormat: (v) => '₪${_money.format(v)}',
              ),
            ],
          ),

          const SizedBox(height: 20),

          // ── Recent Appointments ───────────────────────────────────────
          SectionHeader(
            title: AppStrings.t('recent_appointments', isArabic: isArabic),
          ),

          const SizedBox(height: 8),

          if (_recent.isEmpty)
            EmptyState(
              icon: Icons.calendar_month_outlined,
              message: AppStrings.t('no_appointments_yet', isArabic: isArabic),
            )
          else
            ClinicCard(
              padding: EdgeInsets.zero,
              child: Column(
                children: _recent.asMap().entries.map((entry) {
                  final i = entry.key;
                  final appt = entry.value;
                  final dt = appt.dateTime;
                  return Column(
                    children: [
                      ListTile(
                        contentPadding: const EdgeInsets.symmetric(
                            horizontal: 16, vertical: 6),
                        leading: Container(
                          width: 40,
                          height: 40,
                          decoration: BoxDecoration(
                            color: scheme.primary.withAlpha(20),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Icon(Icons.person_outline,
                              color: scheme.primary, size: 20),
                        ),
                        title: Text(
                          appt.patientName ??
                              '${AppStrings.t('patient', isArabic: isArabic)} #${appt.patientId}',
                          style: const TextStyle(
                              fontWeight: FontWeight.w700, fontSize: 14),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        subtitle: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const SizedBox(height: 2),
                            Text(
                              '${DateFormatHelper.formatDate(dt)}  ·  ${DateFormat('h:mm a').format(dt)}',
                              style: TextStyle(
                                  color: scheme.onSurfaceVariant,
                                  fontSize: 12),
                            ),
                            if (appt.treatmentType != null)
                              Text(
                                appt.treatmentType!,
                                style: TextStyle(
                                    color: scheme.primary,
                                    fontSize: 11,
                                    fontWeight: FontWeight.w600),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                          ],
                        ),
                        trailing: StatusBadge(appt.status),
                        isThreeLine: appt.treatmentType != null,
                      ),
                      if (i < _recent.length - 1)
                        Divider(
                            height: 1,
                            indent: 16,
                            endIndent: 16,
                            color: scheme.outlineVariant),
                    ],
                  );
                }).toList(),
              ),
            ),
        ],
      ),
    );
  }
}
