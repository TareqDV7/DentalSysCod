/// One row of a patient's combined payment history — a follow-up sheet payment
/// or a billing-record payment, merged and shown oldest-first. Mirrors the
/// desktop's `/api/patients/{id}/payment-history`.
class PaymentHistoryEntry {
  final String date;
  final String source; // 'followup' | 'billing'
  final String description;
  final double amount;
  final String? method;

  const PaymentHistoryEntry({
    required this.date,
    required this.source,
    required this.description,
    required this.amount,
    this.method,
  });
}
