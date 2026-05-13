import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:intl/intl.dart';
import '../state/app_state.dart';
import '../services/report_service.dart';
import '../utils/date_format_helper.dart';
import '../widgets/clinic_card.dart';
import '../widgets/section_header.dart';

class ReportsScreen extends StatefulWidget {
  const ReportsScreen({super.key});

  @override
  State<ReportsScreen> createState() => _ReportsScreenState();
}

class _ReportsScreenState extends State<ReportsScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabs;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      body: Column(
        children: [
          Container(
            color: scheme.surface,
            child: TabBar(
              controller: _tabs,
              indicatorColor: scheme.primary,
              labelColor: scheme.primary,
              unselectedLabelColor: scheme.onSurfaceVariant,
              tabs: const [
                Tab(text: 'Weekly'),
                Tab(text: 'Monthly'),
              ],
            ),
          ),
          Expanded(
            child: TabBarView(
              controller: _tabs,
              children: const [
                _WeeklyTab(),
                _MonthlyTab(),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ── Weekly ─────────────────────────────��──────────────────────────────────────

class _WeeklyTab extends StatefulWidget {
  const _WeeklyTab();

  @override
  State<_WeeklyTab> createState() => _WeeklyTabState();
}

class _WeeklyTabState extends State<_WeeklyTab> {
  WeeklyReport? _report;
  bool _loading = false;
  late DateTime _weekStart;
  final _fmt = NumberFormat('#,##0.00', 'en');

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    _weekStart = now.subtract(Duration(days: now.weekday - 1));
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final r = await context.read<AppState>().reports.getWeeklyReport(_weekStart);
    if (mounted) setState(() { _report = r; _loading = false; });
  }

  Future<void> _pickWeek() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _weekStart,
      firstDate: DateTime(2020),
      lastDate: DateTime.now(),
    );
    if (picked != null) {
      final monday = picked.subtract(Duration(days: picked.weekday - 1));
      setState(() => _weekStart = monday);
      _load();
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final weekEnd = _weekStart.add(const Duration(days: 6));
    final weekStartDisplay = DateFormatHelper.formatDate(_weekStart);
    final weekEndDisplay = DateFormatHelper.formatDate(weekEnd);

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        // Week navigator
        ClinicCard(
          child: GestureDetector(
            onTap: _pickWeek,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              child: Text(
                '$weekStartDisplay – $weekEndDisplay',
                textAlign: TextAlign.center,
                style: const TextStyle(fontWeight: FontWeight.w800),
              ),
            ),
          ),
        ),

        const SizedBox(height: 16),

        if (_loading)
          const Center(child: CircularProgressIndicator())
        else if (_report == null)
          Center(
              child: Text('No data',
                  style: TextStyle(color: scheme.onSurfaceVariant)))
        else ...[
          _MetricCard(
            label: 'Distinct Teeth',
            value: '${_report!.distinctTeeth}',
            icon: Icons.medical_services_outlined,
            color: const Color(0xFF0F6D7B),
          ),
          const SizedBox(height: 10),
          _MetricCard(
            label: 'Follow-ups',
            value: '${_report!.followUps}',
            icon: Icons.repeat,
            color: const Color(0xFF7B5DB7),
          ),
          const SizedBox(height: 10),
          _MetricCard(
            label: 'Revenue',
            value: '₪${_fmt.format(_report!.revenue)}',
            icon: Icons.trending_up,
            color: const Color(0xFF1F9A5F),
          ),
          const SizedBox(height: 10),
          _MetricCard(
            label: 'Expenses',
            value: '₪${_fmt.format(_report!.expenses)}',
            icon: Icons.trending_down,
            color: const Color(0xFFD89E1F),
          ),
          const SizedBox(height: 10),
          _MetricCard(
            label: 'Lab Expenses',
            value: '₪${_fmt.format(_report!.labExpenses)}',
            icon: Icons.science_outlined,
            color: const Color(0xFF1D7FB7),
          ),
          const SizedBox(height: 10),
          _MetricCard(
            label: 'Profit',
            value: '₪${_fmt.format(_report!.profit)}',
            icon: Icons.account_balance_wallet,
            color: _report!.profit >= 0
                ? const Color(0xFF1F9A5F)
                : const Color(0xFFD9434E),
          ),
        ],
      ],
    );
  }
}

// ── Monthly ───────────────────────────────���───────────────────────────────────

class _MonthlyTab extends StatefulWidget {
  const _MonthlyTab();

  @override
  State<_MonthlyTab> createState() => _MonthlyTabState();
}

class _MonthlyTabState extends State<_MonthlyTab> {
  List<MonthlyReport> _reports = [];
  bool _loading = true;
  final _fmt = NumberFormat('#,##0.00', 'en');

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final list = await context.read<AppState>().reports.getLast6Months();
    if (mounted) setState(() { _reports = list; _loading = false; });
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_reports.isEmpty) {
      return Center(
          child: Text('No data yet',
              style: TextStyle(color: scheme.onSurfaceVariant)));
    }

    final latest = _reports.last;
    final maxVal = _reports
        .map((r) => r.revenue > r.expenses ? r.revenue : r.expenses)
        .reduce((a, b) => a > b ? a : b);

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        SectionHeader(title: 'Last 6 Months'),
        const SizedBox(height: 8),

        // Bar chart
        ClinicCard(
          padding: const EdgeInsets.all(16),
          child: SizedBox(
            height: 200,
            child: BarChart(
              BarChartData(
                maxY: maxVal * 1.2,
                barGroups: _reports.asMap().entries.map((e) {
                  final r = e.value;
                  return BarChartGroupData(
                    x: e.key,
                    barRods: [
                      BarChartRodData(
                          toY: r.revenue,
                          color: const Color(0xFF0F6D7B),
                          width: 8,
                          borderRadius: BorderRadius.circular(4)),
                      BarChartRodData(
                          toY: r.expenses,
                          color: const Color(0xFFD89E1F),
                          width: 8,
                          borderRadius: BorderRadius.circular(4)),
                    ],
                  );
                }).toList(),
                titlesData: FlTitlesData(
                  bottomTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      getTitlesWidget: (v, _) {
                        final idx = v.toInt();
                        if (idx < 0 || idx >= _reports.length) {
                          return const SizedBox.shrink();
                        }
                        final month = _reports[idx].month;
                        final parts = month.split('-');
                        final label = parts.length >= 2
                            ? DateFormat('MMM').format(
                                DateTime(int.parse(parts[0]),
                                    int.parse(parts[1])))
                            : month;
                        return Text(label,
                            style: TextStyle(
                                fontSize: 10,
                                color: scheme.onSurfaceVariant));
                      },
                    ),
                  ),
                  leftTitles:
                      const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                  topTitles:
                      const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                  rightTitles:
                      const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                ),
                gridData: const FlGridData(show: false),
                borderData: FlBorderData(show: false),
              ),
            ),
          ),
        ),

        const SizedBox(height: 8),

        // Legend
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            _legend('Revenue', const Color(0xFF0F6D7B)),
            const SizedBox(width: 16),
            _legend('Expenses', const Color(0xFFD89E1F)),
          ],
        ),

        const SizedBox(height: 16),

        // Latest month summary
        SectionHeader(
            title:
                'Latest: ${DateFormat('MMMM y').format(DateTime.tryParse('${latest.month}-01') ?? DateTime.now())}'),

        _MetricCard(
          label: 'Visits',
          value: '${latest.visits}',
          icon: Icons.people,
          color: const Color(0xFF0F6D7B),
        ),
        const SizedBox(height: 10),
        _MetricCard(
          label: 'Revenue',
          value: '₪${_fmt.format(latest.revenue)}',
          icon: Icons.trending_up,
          color: const Color(0xFF1F9A5F),
        ),
        const SizedBox(height: 10),
        _MetricCard(
          label: 'Expenses',
          value: '₪${_fmt.format(latest.expenses)}',
          icon: Icons.trending_down,
          color: const Color(0xFFD89E1F),
        ),
        const SizedBox(height: 10),
        _MetricCard(
          label: 'Profit',
          value: '₪${_fmt.format(latest.profit)}',
          icon: Icons.account_balance_wallet,
          color: latest.profit >= 0
              ? const Color(0xFF1F9A5F)
              : const Color(0xFFD9434E),
        ),
      ],
    );
  }

  Widget _legend(String label, Color color) => Row(
        children: [
          Container(
              width: 12,
              height: 12,
              decoration:
                  BoxDecoration(color: color, borderRadius: BorderRadius.circular(3))),
          const SizedBox(width: 4),
          Text(label, style: const TextStyle(fontSize: 12)),
        ],
      );
}

// ── Shared metric card ───────────────────────────���────────────────────────────

class _MetricCard extends StatelessWidget {
  final String label;
  final String value;
  final IconData icon;
  final Color color;

  const _MetricCard({
    required this.label,
    required this.value,
    required this.icon,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return ClinicCard(
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: color.withAlpha(25),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(icon, color: color, size: 20),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Text(label,
                style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 14)),
          ),
          Text(value,
              style: TextStyle(
                  fontWeight: FontWeight.w800, fontSize: 16, color: color)),
        ],
      ),
    );
  }
}
