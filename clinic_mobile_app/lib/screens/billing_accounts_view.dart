import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';
import '../state/app_state.dart';
import '../models/billing_account.dart';
import '../models/patient.dart';
import '../utils/app_strings.dart';
import '../widgets/status_badge.dart';
import '../widgets/empty_state.dart';
import '../widgets/clinic_card.dart';
import 'patient_payment_history_screen.dart';

/// The per-patient billing rollup, sourced from the follow-up sheets. Each row
/// is one patient's charged / paid / balance, so this view and that patient's
/// sheet always show the same numbers. Tapping a row opens the patient's full
/// payment history (sheet payments + invoices merged).
class BillingAccountsView extends StatefulWidget {
  const BillingAccountsView({super.key});

  @override
  State<BillingAccountsView> createState() => _BillingAccountsViewState();
}

class _BillingAccountsViewState extends State<BillingAccountsView> {
  List<BillingAccount> _accounts = [];
  bool _loading = true;
  String _filter = 'all';
  final _searchCtrl = TextEditingController();
  final _fmt = NumberFormat('#,##0.00', 'en');

  @override
  void initState() {
    super.initState();
    _load();
    _searchCtrl.addListener(() {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  void _showError(String message) {
    if (!mounted) return;
    final scheme = Theme.of(context).colorScheme;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), backgroundColor: scheme.error),
    );
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final ar = context.read<AppState>().isArabic;
    try {
      final rows = await context.read<AppState>().billing.getBillingAccounts();
      if (mounted) setState(() { _accounts = rows; _loading = false; });
    } catch (_) {
      if (mounted) setState(() => _loading = false);
      _showError(AppStrings.t('unable_to_load_billing', isArabic: ar));
    }
  }

  void _openHistory(BillingAccount a) {
    // PatientPaymentHistoryScreen only reads id + fullName, so a lightweight
    // Patient built from the rollup row is enough to navigate.
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => PatientPaymentHistoryScreen(
          patient: Patient(
            id: a.patientId,
            firstName: a.patientName,
            lastName: '',
          ),
        ),
      ),
    );
  }

  List<BillingAccount> get _visible {
    final query = _searchCtrl.text.trim().toLowerCase();
    return _accounts.where((a) {
      final matchesFilter = _filter == 'all' || a.status == _filter;
      final matchesQuery =
          query.isEmpty || a.patientName.toLowerCase().contains(query);
      return matchesFilter && matchesQuery;
    }).toList();
  }

  double get _totalBilled => _visible.fold(0, (s, a) => s + a.total);
  double get _totalPaid => _visible.fold(0, (s, a) => s + a.paid);
  double get _totalBalance => _visible.fold(0, (s, a) => s + a.balance);
  int get _openCount => _visible.where((a) => a.balance > 0).length;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final ar = context.watch<AppState>().isArabic;
    if (_loading) return const Center(child: CircularProgressIndicator());

    final visible = _visible;

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(
            AppStrings.t('accounts_hint', isArabic: ar),
            style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 12),
          ),
          const SizedBox(height: 12),
          ClinicCard(
            child: Row(
              children: [
                Expanded(child: _statCell(AppStrings.t('billed', isArabic: ar), '₪${_fmt.format(_totalBilled)}', scheme.primary, scheme)),
                Expanded(child: _statCell(AppStrings.t('paid', isArabic: ar), '₪${_fmt.format(_totalPaid)}', const Color(0xFF1F9A5F), scheme)),
                Expanded(child: _statCell(AppStrings.t('balance', isArabic: ar), '₪${_fmt.format(_totalBalance)}', const Color(0xFFD9434E), scheme)),
                Expanded(child: _statCell(AppStrings.t('open', isArabic: ar), '$_openCount', const Color(0xFF1D7FB7), scheme)),
              ],
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _searchCtrl,
            decoration: InputDecoration(
              hintText: AppStrings.t('search_accounts', isArabic: ar),
              prefixIcon: const Icon(Icons.search),
            ),
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _filterChip(AppStrings.t('all', isArabic: ar), 'all'),
              _filterChip(AppStrings.t('status_paid', isArabic: ar), 'paid'),
              _filterChip(AppStrings.t('status_partial', isArabic: ar), 'partial'),
              _filterChip(AppStrings.t('status_unpaid', isArabic: ar), 'unpaid'),
            ],
          ),
          const SizedBox(height: 14),
          if (visible.isEmpty)
            EmptyState(
              icon: Icons.account_balance_wallet_outlined,
              message: _accounts.isEmpty
                  ? AppStrings.t('no_billing_accounts', isArabic: ar)
                  : AppStrings.t('no_records_match', isArabic: ar),
            )
          else
            ...visible.map((a) => _accountCard(a, scheme, ar)),
          const SizedBox(height: 88),
        ],
      ),
    );
  }

  Widget _accountCard(BillingAccount a, ColorScheme scheme, bool ar) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        color: scheme.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: scheme.outlineVariant),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(18),
          onTap: () => _openHistory(a),
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            a.patientName.isEmpty
                                ? '${AppStrings.t('patient', isArabic: ar)} #${a.patientId}'
                                : a.patientName,
                            style: const TextStyle(fontWeight: FontWeight.w800),
                          ),
                          if (a.lastDate != null && a.lastDate!.isNotEmpty) ...[
                            const SizedBox(height: 4),
                            Text(
                              _displayDate(a.lastDate),
                              style: TextStyle(
                                color: scheme.onSurfaceVariant,
                                fontSize: 12,
                              ),
                            ),
                          ],
                        ],
                      ),
                    ),
                    StatusBadge(a.status),
                    const SizedBox(width: 4),
                    Icon(Icons.chevron_right,
                        size: 20, color: scheme.onSurfaceVariant),
                  ],
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    _amountColumn(AppStrings.t('billed', isArabic: ar), '₪${_fmt.format(a.total)}', scheme),
                    _amountColumn(AppStrings.t('paid', isArabic: ar), '₪${_fmt.format(a.paid)}', scheme),
                    _amountColumn(
                      AppStrings.t('balance', isArabic: ar),
                      '₪${_fmt.format(a.balance)}',
                      scheme,
                      valueColor: a.balance > 0
                          ? const Color(0xFFD9434E)
                          : const Color(0xFF1F9A5F),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _statCell(String label, String value, Color color, ColorScheme scheme) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 11)),
          const SizedBox(height: 4),
          Text(value, style: TextStyle(fontWeight: FontWeight.w800, color: color, fontSize: 14)),
        ],
      ),
    );
  }

  Widget _amountColumn(String label, String value, ColorScheme scheme, {Color? valueColor}) {
    return Expanded(
      child: Column(
        children: [
          Text(value, style: TextStyle(fontWeight: FontWeight.w800, fontSize: 12, color: valueColor ?? scheme.onSurface)),
          const SizedBox(height: 2),
          Text(label, style: TextStyle(fontSize: 10, color: scheme.onSurfaceVariant)),
        ],
      ),
    );
  }

  Widget _filterChip(String label, String value) {
    return ChoiceChip(
      label: Text(label),
      selected: _filter == value,
      onSelected: (_) => setState(() => _filter = value),
    );
  }

  String _displayDate(String? value) {
    if (value == null || value.trim().isEmpty) return '';
    final parsed = DateTime.tryParse(value);
    if (parsed != null) return DateFormat('dd/MM/yyyy').format(parsed);
    return value;
  }
}
