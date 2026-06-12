/// A per-patient billing rollup derived from that patient's follow-up sheet.
///
/// `total` = Σ(price − discount) charged, `paid` = Σ payment, `balance` =
/// total − paid (may be negative → the patient is in credit). This is the exact
/// same math the Receivables view and the patient-page balance use, so the
/// Billing tab and each patient's sheet always agree — one source of truth.
class BillingAccount {
  final int patientId;
  final String patientName;
  final double total;
  final double paid;
  final double balance;
  final String? lastDate;
  final int lineCount;

  const BillingAccount({
    required this.patientId,
    required this.patientName,
    required this.total,
    required this.paid,
    required this.balance,
    this.lastDate,
    this.lineCount = 0,
  });

  /// 'paid' once everything charged is settled (including a patient in credit),
  /// 'partial' while some money has come in, otherwise 'unpaid'. Mirrors
  /// [BillingRecord.statusLabel] semantics so both views read the same.
  String get status {
    if (total > 0 && paid >= total) return 'paid';
    if (paid > 0) return 'partial';
    return 'unpaid';
  }

  factory BillingAccount.fromRow(Map<String, dynamic> row) => BillingAccount(
        patientId: (row['id'] as num).toInt(),
        patientName: (row['patient_name'] ?? '').toString().trim(),
        total: _d(row['total']),
        paid: _d(row['paid']),
        balance: _d(row['balance']),
        lastDate: row['last_date'] as String?,
        lineCount: (row['line_count'] as num?)?.toInt() ?? 0,
      );

  static double _d(dynamic v) =>
      v is num ? v.toDouble() : double.tryParse(v?.toString() ?? '') ?? 0;
}
