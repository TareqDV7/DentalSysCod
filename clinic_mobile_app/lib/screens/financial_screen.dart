import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';
import '../state/app_state.dart';
import '../models/billing_record.dart';
import '../models/expense.dart';
import '../models/patient.dart';
import '../utils/amount_expr.dart';
import '../utils/app_strings.dart';
import '../widgets/status_badge.dart';
import '../widgets/empty_state.dart';
import '../widgets/gradient_button.dart';
import '../widgets/clinic_card.dart';
import 'billing_accounts_view.dart';

class FinancialScreen extends StatefulWidget {
  const FinancialScreen({super.key});

  @override
  State<FinancialScreen> createState() => _FinancialScreenState();
}

class _FinancialScreenState extends State<FinancialScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabs;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 3, vsync: this);
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final ar = context.watch<AppState>().isArabic;
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
              tabs: [
                Tab(text: AppStrings.t('billing', isArabic: ar)),
                Tab(text: AppStrings.t('expenses', isArabic: ar)),
                Tab(text: AppStrings.t('receivables', isArabic: ar)),
              ],
            ),
          ),
          Expanded(
            child: TabBarView(
              controller: _tabs,
              children: const [
                _BillingTab(),
                _ExpensesTab(),
                _ReceivablesTab(),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ── Billing tab ───────────────────────────────────────────────────────────────

class _BillingTab extends StatefulWidget {
  const _BillingTab();

  @override
  State<_BillingTab> createState() => _BillingTabState();
}

class _BillingTabState extends State<_BillingTab> {
  // false = Accounts (rolled up from the patient sheets — the default view),
  // true = Invoices (standalone billing records added here).
  bool _showInvoices = false;

  @override
  Widget build(BuildContext context) {
    final ar = context.watch<AppState>().isArabic;
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
          child: SizedBox(
            width: double.infinity,
            child: SegmentedButton<bool>(
              segments: [
                ButtonSegment(
                  value: false,
                  label: Text(AppStrings.t('accounts', isArabic: ar)),
                  icon: const Icon(
                      Icons.account_balance_wallet_outlined, size: 18),
                ),
                ButtonSegment(
                  value: true,
                  label: Text(AppStrings.t('invoices', isArabic: ar)),
                  icon: const Icon(Icons.receipt_long_outlined, size: 18),
                ),
              ],
              selected: {_showInvoices},
              onSelectionChanged: (s) =>
                  setState(() => _showInvoices = s.first),
              showSelectedIcon: false,
            ),
          ),
        ),
        Expanded(
          child: _showInvoices
              ? const _InvoicesView()
              : const BillingAccountsView(),
        ),
      ],
    );
  }
}

class _InvoicesView extends StatefulWidget {
  const _InvoicesView();

  @override
  State<_InvoicesView> createState() => _InvoicesViewState();
}

class _InvoicesViewState extends State<_InvoicesView> {
  List<BillingRecord> _records = [];
  bool _loading = true;
  String _filter = 'all';
  final _searchCtrl = TextEditingController();
  final _fmt = NumberFormat('#,##0.00', 'en');

  void _showError(String message) {
    if (!mounted) return;
    final scheme = Theme.of(context).colorScheme;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: scheme.error,
      ),
    );
  }

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

  Future<void> _load() async {
    setState(() => _loading = true);
    final ar = context.read<AppState>().isArabic;
    try {
      final records = await context.read<AppState>().billing.getBillingRecords();
      if (mounted) setState(() { _records = records; _loading = false; });
    } catch (_) {
      if (mounted) setState(() => _loading = false);
      _showError(AppStrings.t('unable_to_load_billing', isArabic: ar));
    }
  }

  void _addBilling() {
    final ar = context.read<AppState>().isArabic;
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _AddBillingSheet(
        onSaved: (b) async {
          try {
            await context.read<AppState>().billing.addBillingRecord(b);
            if (mounted) {
              // Push the new receipt now (parity with delete) so other devices
              // — and the kept-alive dashboard via the sync stream — see it.
              unawaited(context.read<AppState>().sync.syncNow());
              _load();
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                    content:
                        Text(AppStrings.t('billing_saved', isArabic: ar))),
              );
            }
          } catch (error) {
            _showError(error.toString());
            rethrow;
          }
        },
      ),
    );
  }

  Future<void> _deleteBilling(BillingRecord b) async {
    if (b.id == null) return;
    final ar = context.read<AppState>().isArabic;
    final messenger = ScaffoldMessenger.of(context);
    final state = context.read<AppState>();
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(AppStrings.t('delete_billing', isArabic: ar)),
        content: Text(
          b.creditUsed > 0
              ? '${AppStrings.t('delete_billing_credit_prefix', isArabic: ar)}₪${_fmt.format(b.creditUsed)}${AppStrings.t('delete_billing_credit_suffix', isArabic: ar)}'
              : AppStrings.t('delete_billing_q', isArabic: ar),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: Text(AppStrings.t('cancel', isArabic: ar))),
          TextButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: Text(AppStrings.t('delete', isArabic: ar),
                  style: const TextStyle(color: Color(0xFFD9434E)))),
        ],
      ),
    );
    if (confirm != true) return;
    try {
      await state.billing.deleteBillingRecord(b.id!);
      unawaited(state.sync.syncNow());
      if (mounted) {
        await _load();
        messenger.showSnackBar(SnackBar(
            content: Text(AppStrings.t('billing_deleted', isArabic: ar))));
      }
    } catch (error) {
      _showError(error.toString());
    }
  }

  List<BillingRecord> get _visibleRecords {
    final query = _searchCtrl.text.trim().toLowerCase();
    return _records.where((record) {
      final status = record.statusLabel.toLowerCase();
      final matchesFilter = _filter == 'all' || status == _filter;
      final searchable = [
        record.patientName ?? '',
        record.paymentDate ?? '',
        record.paymentMethod ?? '',
        record.statusLabel,
        record.total.toStringAsFixed(2),
        record.paidAmount.toStringAsFixed(2),
        record.balanceDue.toStringAsFixed(2),
      ].join(' ').toLowerCase();
      return matchesFilter && (query.isEmpty || searchable.contains(query));
    }).toList();
  }

  double get _totalBilled => _visibleRecords.fold(0, (sum, record) => sum + record.total);
  double get _totalPaid => _visibleRecords.fold(0, (sum, record) => sum + record.paidAmount);
  double get _totalBalance => _visibleRecords.fold(0, (sum, record) => sum + record.balanceDue);
  int get _unpaidCount => _visibleRecords.where((record) => record.balanceDue > 0).length;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final ar = context.watch<AppState>().isArabic;
    if (_loading) return const Center(child: CircularProgressIndicator());

    final visible = _visibleRecords;

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  AppStrings.t('invoices', isArabic: ar),
                  style: Theme.of(context).textTheme.titleLarge?.copyWith(
                        fontWeight: FontWeight.w800,
                      ),
                ),
              ),
              TextButton.icon(
                onPressed: _addBilling,
                icon: const Icon(Icons.add),
                label: Text(AppStrings.t('add_billing', isArabic: ar)),
              ),
            ],
          ),
          Text(
            AppStrings.t('invoices_hint', isArabic: ar),
            style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 12),
          ),
          const SizedBox(height: 10),
          ClinicCard(
            child: Row(
              children: [
                Expanded(child: _statCell(AppStrings.t('billed', isArabic: ar), '₪${_fmt.format(_totalBilled)}', scheme.primary, scheme)),
                Expanded(child: _statCell(AppStrings.t('paid', isArabic: ar), '₪${_fmt.format(_totalPaid)}', const Color(0xFF1F9A5F), scheme)),
                Expanded(child: _statCell(AppStrings.t('balance', isArabic: ar), '₪${_fmt.format(_totalBalance)}', const Color(0xFFD9434E), scheme)),
                Expanded(child: _statCell(AppStrings.t('open', isArabic: ar), '$_unpaidCount', const Color(0xFF1D7FB7), scheme)),
              ],
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _searchCtrl,
            decoration: InputDecoration(
              hintText: AppStrings.t('search_billing', isArabic: ar),
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
              icon: Icons.receipt_long_outlined,
              message: _records.isEmpty
                  ? AppStrings.t('no_billing_records', isArabic: ar)
                  : AppStrings.t('no_records_match', isArabic: ar),
              actionLabel:
                  _records.isEmpty ? AppStrings.t('add_record', isArabic: ar) : null,
              onAction: _records.isEmpty ? _addBilling : null,
            )
          else
            ...visible.map((b) {
              return Container(
                margin: const EdgeInsets.only(bottom: 10),
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: scheme.surface,
                  borderRadius: BorderRadius.circular(18),
                  border: Border.all(color: scheme.outlineVariant),
                ),
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
                                b.patientName ??
                                    '${AppStrings.t('patient', isArabic: ar)} #${b.patientId}',
                                style: const TextStyle(fontWeight: FontWeight.w800),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                _displayDate(b.paymentDate) ??
                                    AppStrings.t('no_payment_date', isArabic: ar),
                                style: TextStyle(
                                  color: scheme.onSurfaceVariant,
                                  fontSize: 12,
                                ),
                              ),
                              if (b.paymentMethod != null) ...[
                                const SizedBox(height: 2),
                                Text(
                                  b.paymentMethod!,
                                  style: TextStyle(
                                    color: scheme.onSurfaceVariant,
                                    fontSize: 12,
                                  ),
                                ),
                              ],
                            ],
                          ),
                        ),
                        StatusBadge(b.statusLabel.toLowerCase()),
                        PopupMenuButton<String>(
                          icon: const Icon(Icons.more_vert, size: 20),
                          onSelected: (v) {
                            if (v == 'delete') _deleteBilling(b);
                          },
                          itemBuilder: (_) => [
                            PopupMenuItem(
                              value: 'delete',
                              child: ListTile(
                                contentPadding: EdgeInsets.zero,
                                leading: const Icon(Icons.delete_outline,
                                    color: Color(0xFFD9434E)),
                                title: Text(AppStrings.t('delete', isArabic: ar)),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        _amountColumn(AppStrings.t('subtotal', isArabic: ar), '₪${_fmt.format(b.subtotal)}', scheme),
                        _amountColumn(AppStrings.t('discount', isArabic: ar), '₪${_fmt.format(b.discount)}', scheme),
                        _amountColumn(AppStrings.t('paid', isArabic: ar), '₪${_fmt.format(b.paidAmount)}', scheme),
                        _amountColumn(AppStrings.t('balance', isArabic: ar), '₪${_fmt.format(b.balanceDue)}', scheme,
                            valueColor: b.balanceDue > 0 ? const Color(0xFFD9434E) : const Color(0xFF1F9A5F)),
                      ],
                    ),
                    if (b.creditUsed > 0) ...[
                      const SizedBox(height: 6),
                      Text('${AppStrings.t('credit_applied', isArabic: ar)}: ₪${_fmt.format(b.creditUsed)}',
                          style: TextStyle(
                              fontSize: 12, color: scheme.onSurfaceVariant)),
                    ],
                  ],
                ),
              );
            }),
          const SizedBox(height: 88),
        ],
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
    final selected = _filter == value;
    return ChoiceChip(
      label: Text(label),
      selected: selected,
      onSelected: (_) => setState(() => _filter = value),
    );
  }

  String? _displayDate(String? value) {
    if (value == null || value.trim().isEmpty) return null;
    final parsed = DateTime.tryParse(value);
    if (parsed != null) {
      return DateFormat('dd/MM/yyyy').format(parsed);
    }
    return value;
  }
}

// ── Expenses tab ──────────────────────────────────────────────────────────────

class _ExpensesTab extends StatefulWidget {
  const _ExpensesTab();

  @override
  State<_ExpensesTab> createState() => _ExpensesTabState();
}

class _ExpensesTabState extends State<_ExpensesTab> {
  List<Expense> _expenses = [];
  bool _loading = true;
  String _period = 'all';
  String _status = 'all';
  final _fmt = NumberFormat('#,##0.00', 'en');

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final list = await context
        .read<AppState>()
        .billing
        .getExpenses(period: _period, status: _status);
    if (mounted) setState(() { _expenses = list; _loading = false; });
  }

  void _addExpense() {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _AddExpenseSheet(
        onSaved: (e) async {
          await context.read<AppState>().billing.addExpense(e);
          if (mounted) {
            unawaited(context.read<AppState>().sync.syncNow());
            _load();
          }
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final ar = context.watch<AppState>().isArabic;
    final total = _expenses.fold(0.0, (s, e) => s + e.amount);

    return Scaffold(
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
            child: Row(
              children: [
                _chip(AppStrings.t('all', isArabic: ar), 'all', _period,
                    (v) => setState(() { _period = v; _load(); })),
                const SizedBox(width: 6),
                _chip(AppStrings.t('today', isArabic: ar), 'today', _period,
                    (v) => setState(() { _period = v; _load(); })),
                const SizedBox(width: 6),
                _chip(AppStrings.t('month', isArabic: ar), 'month', _period,
                    (v) => setState(() { _period = v; _load(); })),
                const Spacer(),
                _chip(AppStrings.t('status_paid', isArabic: ar), 'paid', _status,
                    (v) => setState(() {
                          _status = _status == v ? 'all' : v;
                          _load();
                        })),
              ],
            ),
          ),
          if (!_loading && _expenses.isNotEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 10, 16, 0),
              child: ClinicCard(
                padding: const EdgeInsets.symmetric(
                    horizontal: 16, vertical: 10),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(AppStrings.t('total_expenses', isArabic: ar),
                        style: TextStyle(
                            color: scheme.onSurfaceVariant,
                            fontWeight: FontWeight.w600)),
                    Text('₪${_fmt.format(total)}',
                        style: const TextStyle(
                            fontWeight: FontWeight.w800,
                            fontSize: 16,
                            color: Color(0xFFD9434E))),
                  ],
                ),
              ),
            ),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _expenses.isEmpty
                    ? EmptyState(
                        icon: Icons.money_off_outlined,
                        message: AppStrings.t('no_expenses_found', isArabic: ar),
                        actionLabel: AppStrings.t('add_expense', isArabic: ar),
                        onAction: _addExpense,
                      )
                    : RefreshIndicator(
                        onRefresh: _load,
                        child: ListView.builder(
                          padding: const EdgeInsets.all(16),
                          itemCount: _expenses.length,
                          itemBuilder: (_, i) {
                            final e = _expenses[i];
                            return Container(
                              margin: const EdgeInsets.only(bottom: 8),
                              padding: const EdgeInsets.all(14),
                              decoration: BoxDecoration(
                                color: scheme.surface,
                                borderRadius: BorderRadius.circular(16),
                                border: Border.all(
                                    color: scheme.outlineVariant),
                              ),
                              child: Row(
                                children: [
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      children: [
                                        Text(e.category,
                                            style: const TextStyle(
                                                fontWeight: FontWeight.w700)),
                                        if (e.vendor != null)
                                          Text(e.vendor!,
                                              style: TextStyle(
                                                  color: scheme.onSurfaceVariant,
                                                  fontSize: 12)),
                                        Text(
                                            (e.expenseDate?.isNotEmpty ?? false)
                                                ? e.expenseDate!
                                                : '—',
                                            style: TextStyle(
                                                color: scheme.onSurfaceVariant,
                                                fontSize: 12)),
                                      ],
                                    ),
                                  ),
                                  Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.end,
                                    children: [
                                      Text('₪${_fmt.format(e.amount)}',
                                          style: const TextStyle(
                                              fontWeight: FontWeight.w800)),
                                      const SizedBox(height: 4),
                                      StatusBadge(e.status),
                                    ],
                                  ),
                                ],
                              ),
                            );
                          },
                        ),
                      ),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _addExpense,
        backgroundColor: scheme.primary,
        foregroundColor: Colors.white,
        icon: const Icon(Icons.add),
        label: Text(AppStrings.t('add_expense', isArabic: ar),
            style: const TextStyle(fontWeight: FontWeight.w700)),
      ),
    );
  }

  Widget _chip(String label, String value, String current,
      void Function(String) onTap) {
    final selected = current == value;
    return GestureDetector(
      onTap: () => onTap(value),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: selected
              ? const Color(0xFF0F6D7B)
              : Theme.of(context).colorScheme.surface,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
              color: selected
                  ? const Color(0xFF0F6D7B)
                  : Theme.of(context).colorScheme.outlineVariant),
        ),
        child: Text(label,
            style: TextStyle(
                color: selected ? Colors.white : null,
                fontWeight: FontWeight.w600,
                fontSize: 12)),
      ),
    );
  }
}

// ── Receivables tab ───────────────────────────────────────────────────────────

class _ReceivablesTab extends StatefulWidget {
  const _ReceivablesTab();

  @override
  State<_ReceivablesTab> createState() => _ReceivablesTabState();
}

class _ReceivablesTabState extends State<_ReceivablesTab> {
  List<Map<String, dynamic>> _rows = [];
  bool _loading = true;
  final _fmt = NumberFormat('#,##0.00', 'en');

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final rows = await context.read<AppState>().billing.getReceivables();
    if (mounted) setState(() { _rows = rows; _loading = false; });
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final ar = context.watch<AppState>().isArabic;
    final totalOwed = _rows.fold(
        0.0, (s, r) => s + (r['balance'] as num? ?? 0).toDouble());

    if (_loading) return const Center(child: CircularProgressIndicator());

    return RefreshIndicator(
      onRefresh: _load,
      child: _rows.isEmpty
          ? EmptyState(
              icon: Icons.check_circle_outline,
              message: AppStrings.t('no_outstanding', isArabic: ar),
            )
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                ClinicCard(
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(AppStrings.t('total_receivables', isArabic: ar),
                              style: TextStyle(
                                  color: scheme.onSurfaceVariant,
                                  fontSize: 13)),
                          Text('₪${_fmt.format(totalOwed)}',
                              style: const TextStyle(
                                  fontWeight: FontWeight.w800,
                                  fontSize: 20,
                                  color: Color(0xFFD9434E))),
                        ],
                      ),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          Text('${_rows.length}',
                              style: TextStyle(
                                  fontWeight: FontWeight.w800,
                                  fontSize: 20,
                                  color: scheme.primary)),
                          Text(AppStrings.t('patients_label', isArabic: ar),
                              style: TextStyle(
                                  color: scheme.onSurfaceVariant,
                                  fontSize: 13)),
                        ],
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 12),
                ..._rows.map((r) {
                  final balance =
                      (r['balance'] as num? ?? 0).toDouble();
                  return Container(
                    margin: const EdgeInsets.only(bottom: 8),
                    padding: const EdgeInsets.all(14),
                    decoration: BoxDecoration(
                      color: scheme.surface,
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(color: scheme.outlineVariant),
                    ),
                    child: Column(
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text(
                                (r['patient_name'] as String?)?.isNotEmpty ==
                                        true
                                    ? r['patient_name'] as String
                                    : '—',
                                style: const TextStyle(
                                    fontWeight: FontWeight.w700)),
                            Text('₪${_fmt.format(balance)}',
                                style: const TextStyle(
                                    fontWeight: FontWeight.w800,
                                    color: Color(0xFFD9434E))),
                          ],
                        ),
                        const SizedBox(height: 8),
                        Row(
                          children: [
                            _infoCol(
                                AppStrings.t('total', isArabic: ar),
                                '₪${_fmt.format((r['total'] as num? ?? 0).toDouble())}',
                                scheme),
                            _infoCol(
                                AppStrings.t('paid', isArabic: ar),
                                '₪${_fmt.format((r['paid'] as num? ?? 0).toDouble())}',
                                scheme),
                            _infoCol(
                                AppStrings.t('last_payment', isArabic: ar),
                                r['last_date'] ?? '—',
                                scheme),
                          ],
                        ),
                      ],
                    ),
                  );
                }),
              ],
            ),
    );
  }

  Widget _infoCol(String label, String value, ColorScheme scheme) =>
      Expanded(
        child: Column(
          children: [
            Text(value,
                style: const TextStyle(
                    fontWeight: FontWeight.w600, fontSize: 12)),
            Text(label,
                style: TextStyle(
                    color: scheme.onSurfaceVariant, fontSize: 10)),
          ],
        ),
      );
}

// ── Add Billing sheet ─────────────────────────────────────────────────────────

class _AddBillingSheet extends StatefulWidget {
  final Future<void> Function(BillingRecord) onSaved;
  const _AddBillingSheet({required this.onSaved});

  @override
  State<_AddBillingSheet> createState() => _AddBillingSheetState();
}

class _AddBillingSheetState extends State<_AddBillingSheet> {
  Patient? _patient;
  List<Patient> _patients = [];
  final _subtotal = TextEditingController();
  final _discount = TextEditingController(text: '0');
  final _paid = TextEditingController();
  String _method = 'Cash';
  bool _saving = false;

  void _showError(String message) {
    if (!mounted) return;
    final scheme = Theme.of(context).colorScheme;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: scheme.error,
      ),
    );
  }

  @override
  void initState() {
    super.initState();
    _loadPatients();
  }

  Future<void> _loadPatients() async {
    final ar = context.read<AppState>().isArabic;
    try {
      final list = await context.read<AppState>().patients.getPatients();
      if (mounted) setState(() => _patients = list);
    } catch (_) {
      _showError(AppStrings.t('unable_to_load_patients', isArabic: ar));
    }
  }

  /// Display label for a payment method; the stored value stays the English
  /// token (Cash/Card/…) so it matches the desktop + server, only the shown
  /// text is localized.
  String _methodLabel(String m, bool ar) {
    switch (m) {
      case 'Cash':
        return AppStrings.t('method_cash', isArabic: ar);
      case 'Card':
        return AppStrings.t('method_card', isArabic: ar);
      case 'Bank Transfer':
        return AppStrings.t('method_bank_transfer', isArabic: ar);
      case 'Insurance':
        return AppStrings.t('method_insurance', isArabic: ar);
      default:
        return m;
    }
  }

  Future<void> _save() async {
    if (_patient == null) return;
    final ar = context.read<AppState>().isArabic;
    final subtotal = AmountExpr.parse(_subtotal.text);
    final discount = AmountExpr.parse(_discount.text);
    final paid = AmountExpr.parse(_paid.text);
    // A billing entry must carry money: a charge, a payment, or both. A
    // payment-only receipt (charge 0, paid > 0) draws down the patient's balance.
    if (subtotal.value <= 0 && paid.value <= 0) {
      _showError(AppStrings.t('billing_needs_amount', isArabic: ar));
      return;
    }
    setState(() => _saving = true);
    try {
      await widget.onSaved(BillingRecord(
        patientId: _patient!.id!,
        patientName: _patient!.fullName,
        subtotal: subtotal.value,
        discount: discount.value,
        paidAmount: paid.value,
        subtotalExpr: subtotal.expr,
        discountExpr: discount.expr,
        paidAmountExpr: paid.expr,
        paymentMethod: _method,
        paymentDate: DateTime.now().toIso8601String().substring(0, 10),
      ));
      if (mounted) Navigator.pop(context);
    } catch (error) {
      _showError(error.toString());
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  void dispose() {
    for (final c in [_subtotal, _discount, _paid]) {
      c.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final ar = context.watch<AppState>().isArabic;
    return DraggableScrollableSheet(
      initialChildSize: 0.8,
      minChildSize: 0.5,
      maxChildSize: 0.95,
      builder: (_, scroll) => Container(
        decoration: BoxDecoration(
          color: Theme.of(context).scaffoldBackgroundColor,
          borderRadius:
              const BorderRadius.vertical(top: Radius.circular(24)),
        ),
        child: SafeArea(
          top: false,
          child: Column(
            children: [
              const SizedBox(height: 8),
              Container(
                  width: 40, height: 4,
                  decoration: BoxDecoration(
                      color: scheme.outlineVariant,
                      borderRadius: BorderRadius.circular(2))),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
                child: Row(children: [
                  Text(AppStrings.t('add_billing', isArabic: ar),
                      style: Theme.of(context).textTheme.titleLarge),
                  const Spacer(),
                  IconButton(
                      onPressed: () => Navigator.pop(context),
                      icon: const Icon(Icons.close)),
                ]),
              ),
              Expanded(
                child: ListView(
                  controller: scroll,
                  padding: const EdgeInsets.all(16),
                  children: [
                  DropdownButtonFormField<Patient>(
                    initialValue: _patient,
                    decoration: InputDecoration(
                        labelText: AppStrings.t('patient', isArabic: ar)),
                    items: _patients
                        .map((p) => DropdownMenuItem(
                            value: p, child: Text(p.fullName)))
                        .toList(),
                    onChanged: (p) => setState(() => _patient = p),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                      controller: _subtotal,
                      decoration: InputDecoration(
                          labelText:
                              '${AppStrings.t('charge', isArabic: ar)} (₪)',
                          helperText:
                              AppStrings.t('charge_payment_hint', isArabic: ar),
                          prefixText: '₪ '),
                      keyboardType: TextInputType.text),
                  const SizedBox(height: 12),
                  TextField(
                      controller: _discount,
                      decoration: InputDecoration(
                          labelText:
                              '${AppStrings.t('discount', isArabic: ar)} (₪)',
                          prefixText: '₪ '),
                      keyboardType: TextInputType.text),
                  const SizedBox(height: 12),
                  TextField(
                      controller: _paid,
                      decoration: InputDecoration(
                          labelText:
                              '${AppStrings.t('amount_paid', isArabic: ar)} (₪)',
                          prefixText: '₪ '),
                      keyboardType: TextInputType.text),
                  const SizedBox(height: 12),
                  DropdownButtonFormField<String>(
                    initialValue: _method,
                    decoration: InputDecoration(
                        labelText:
                            AppStrings.t('payment_method', isArabic: ar)),
                    items: ['Cash', 'Card', 'Bank Transfer', 'Insurance']
                        .map((m) => DropdownMenuItem(
                            value: m, child: Text(_methodLabel(m, ar))))
                        .toList(),
                    onChanged: (v) => setState(() => _method = v!),
                  ),
                  const SizedBox(height: 20),
                  GradientButton(
                    label: AppStrings.t('save', isArabic: ar),
                    loading: _saving,
                    onPressed: (_saving || _patient == null) ? null : _save,
                    width: double.infinity,
                  ),
                  const SizedBox(height: 16),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ── Add Expense sheet ─────────────────────────────────────────────────────────

class _AddExpenseSheet extends StatefulWidget {
  final Future<void> Function(Expense) onSaved;
  const _AddExpenseSheet({required this.onSaved});

  @override
  State<_AddExpenseSheet> createState() => _AddExpenseSheetState();
}

class _AddExpenseSheetState extends State<_AddExpenseSheet> {
  final _category = TextEditingController();
  final _amount = TextEditingController();
  final _vendor = TextEditingController();
  final _notes = TextEditingController();
  String _status = 'paid';
  bool _saving = false;

  void _showError(String message) {
    if (!mounted) return;
    final scheme = Theme.of(context).colorScheme;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: scheme.error,
      ),
    );
  }

  @override
  void dispose() {
    for (final c in [_category, _amount, _vendor, _notes]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _save() async {
    if (_category.text.trim().isEmpty) return;
    setState(() => _saving = true);
    try {
      await widget.onSaved(Expense(
        category: _category.text.trim(),
        amount: double.tryParse(_amount.text) ?? 0,
        vendor: _vendor.text.trim().isEmpty ? null : _vendor.text.trim(),
        notes: _notes.text.trim().isEmpty ? null : _notes.text.trim(),
        status: _status,
      ));
      if (mounted) Navigator.pop(context);
    } catch (error) {
      _showError(error.toString());
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final ar = context.watch<AppState>().isArabic;
    return DraggableScrollableSheet(
      initialChildSize: 0.75,
      minChildSize: 0.4,
      maxChildSize: 0.95,
      builder: (_, scroll) => Container(
        decoration: BoxDecoration(
          color: Theme.of(context).scaffoldBackgroundColor,
          borderRadius:
              const BorderRadius.vertical(top: Radius.circular(24)),
        ),
        child: SafeArea(
          top: false,
          child: Column(
            children: [
              const SizedBox(height: 8),
              Container(
                  width: 40, height: 4,
                  decoration: BoxDecoration(
                      color: scheme.outlineVariant,
                      borderRadius: BorderRadius.circular(2))),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
                child: Row(children: [
                  Text(AppStrings.t('add_expense', isArabic: ar),
                      style: Theme.of(context).textTheme.titleLarge),
                  const Spacer(),
                  IconButton(
                      onPressed: () => Navigator.pop(context),
                      icon: const Icon(Icons.close)),
                ]),
              ),
              Expanded(
                child: ListView(
                  controller: scroll,
                  padding: const EdgeInsets.all(16),
                  children: [
                  TextField(
                      controller: _category,
                      decoration: InputDecoration(
                          labelText: AppStrings.t('category', isArabic: ar))),
                  const SizedBox(height: 12),
                  TextField(
                      controller: _amount,
                      decoration: InputDecoration(
                          labelText:
                              '${AppStrings.t('amount', isArabic: ar)} (₪)',
                          prefixText: '₪ '),
                      keyboardType: TextInputType.number),
                  const SizedBox(height: 12),
                  TextField(
                      controller: _vendor,
                      decoration: InputDecoration(
                          labelText:
                              AppStrings.t('vendor_optional', isArabic: ar))),
                  const SizedBox(height: 12),
                  DropdownButtonFormField<String>(
                    initialValue: _status,
                    decoration: InputDecoration(
                        labelText: AppStrings.t('status', isArabic: ar)),
                    items: [
                      DropdownMenuItem(
                          value: 'paid',
                          child:
                              Text(AppStrings.t('status_paid', isArabic: ar))),
                      DropdownMenuItem(
                          value: 'postponed',
                          child: Text(
                              AppStrings.t('status_postponed', isArabic: ar))),
                    ],
                    onChanged: (v) => setState(() => _status = v!),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                      controller: _notes,
                      decoration: InputDecoration(
                          labelText: AppStrings.t('notes', isArabic: ar)),
                      maxLines: 2),
                  const SizedBox(height: 20),
                  GradientButton(
                    label: AppStrings.t('save_expense', isArabic: ar),
                    loading: _saving,
                    onPressed: _saving ? null : _save,
                    width: double.infinity,
                  ),
                  const SizedBox(height: 16),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
