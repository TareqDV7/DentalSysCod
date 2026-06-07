import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';
import '../state/app_state.dart';
import '../models/patient.dart';
import '../models/payment_history_entry.dart';
import '../utils/app_strings.dart';
import '../utils/date_format_helper.dart';
import '../widgets/empty_state.dart';

/// A patient's combined payment history: follow-up sheet payments + billing
/// records, oldest-first, with a Total Collected footer. Desktop parity with
/// `/api/patients/{id}/payment-history`.
class PatientPaymentHistoryScreen extends StatefulWidget {
  final Patient patient;
  const PatientPaymentHistoryScreen({super.key, required this.patient});

  @override
  State<PatientPaymentHistoryScreen> createState() =>
      _PatientPaymentHistoryScreenState();
}

class _PatientPaymentHistoryScreenState
    extends State<PatientPaymentHistoryScreen> {
  final _fmt = NumberFormat('#,##0.00');
  List<PaymentHistoryEntry> _entries = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final db = context.read<AppState>().db;
    final list = await db.getPatientPaymentHistory(widget.patient.id!);
    if (mounted) {
      setState(() {
        _entries = list;
        _loading = false;
      });
    }
  }

  String _displayDate(String raw) {
    final dt = DateFormatHelper.parseApiDate(raw) ??
        DateFormatHelper.parseDisplayDate(raw);
    return dt == null ? raw : DateFormatHelper.formatDate(dt);
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final ar = context.watch<AppState>().isArabic;
    final total = _entries.fold<double>(0, (s, e) => s + e.amount);

    return Scaffold(
      appBar: AppBar(
          title: Text(
              '${widget.patient.fullName} · ${AppStrings.t('payments', isArabic: ar)}')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _entries.isEmpty
              ? EmptyState(
                  icon: Icons.payments_outlined,
                  message: AppStrings.t('no_payments_recorded', isArabic: ar))
              : Column(
                  children: [
                    Expanded(
                      child: ListView.separated(
                        padding: const EdgeInsets.all(16),
                        itemCount: _entries.length,
                        separatorBuilder: (_, _) => const SizedBox(height: 8),
                        itemBuilder: (context, i) {
                          final e = _entries[i];
                          final isFollowup = e.source == 'followup';
                          return Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 14, vertical: 12),
                            decoration: BoxDecoration(
                              color: scheme.surface,
                              borderRadius: BorderRadius.circular(16),
                              border: Border.all(color: scheme.outlineVariant),
                            ),
                            child: Row(
                              children: [
                                Icon(
                                    isFollowup
                                        ? Icons.medical_services_outlined
                                        : Icons.receipt_long_outlined,
                                    color: scheme.primary,
                                    size: 20),
                                const SizedBox(width: 12),
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                          e.description.isEmpty
                                              ? (isFollowup
                                                  ? AppStrings.t('followup',
                                                      isArabic: ar)
                                                  : AppStrings.t(
                                                      'billing_record',
                                                      isArabic: ar))
                                              : e.description,
                                          style: const TextStyle(
                                              fontWeight: FontWeight.w700)),
                                      Text(
                                          [
                                            _displayDate(e.date),
                                            if (e.method != null &&
                                                e.method!.isNotEmpty)
                                              e.method!,
                                            isFollowup
                                                ? AppStrings.t('followup',
                                                    isArabic: ar)
                                                : AppStrings.t('billing',
                                                    isArabic: ar)
                                          ].join(' · '),
                                          style: TextStyle(
                                              fontSize: 12,
                                              color: scheme.onSurfaceVariant)),
                                    ],
                                  ),
                                ),
                                Column(
                                  crossAxisAlignment: CrossAxisAlignment.end,
                                  children: [
                                    Text('₪${_fmt.format(e.amount)}',
                                        style: const TextStyle(
                                            fontWeight: FontWeight.w800)),
                                    if (e.creditUsed > 0)
                                      Text(
                                          '+₪${_fmt.format(e.creditUsed)} ${AppStrings.t('credit', isArabic: ar)}',
                                          style: TextStyle(
                                              fontSize: 11,
                                              color: scheme.onSurfaceVariant)),
                                  ],
                                ),
                              ],
                            ),
                          );
                        },
                      ),
                    ),
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: scheme.primary.withAlpha(18),
                        border: Border(
                            top: BorderSide(color: scheme.outlineVariant)),
                      ),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(AppStrings.t('total_collected', isArabic: ar),
                              style: const TextStyle(fontWeight: FontWeight.w700)),
                          Text('₪${_fmt.format(total)}',
                              style: TextStyle(
                                  fontWeight: FontWeight.w900,
                                  fontSize: 16,
                                  color: scheme.primary)),
                        ],
                      ),
                    ),
                  ],
                ),
    );
  }
}
