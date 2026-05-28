class BillingRecord {
  final int? id;
  final int patientId;
  final String? patientName;
  final double subtotal;
  final double discount;
  final double paidAmount;
  final double creditUsed;
  final String? paymentMethod;
  final String? paymentDate;
  // Verbatim arithmetic the user typed ("20+20"), kept for display. null = plain.
  final String? subtotalExpr;
  final String? discountExpr;
  final String? paidAmountExpr;
  final String? updatedAt;
  final bool isSynced;

  BillingRecord({
    this.id,
    required this.patientId,
    this.patientName,
    required this.subtotal,
    this.discount = 0,
    required this.paidAmount,
    this.creditUsed = 0,
    this.paymentMethod,
    this.paymentDate,
    this.subtotalExpr,
    this.discountExpr,
    this.paidAmountExpr,
    this.updatedAt,
    this.isSynced = false,
  });

  double get total => subtotal - discount;
  double get balanceDue => total - paidAmount - creditUsed;

  String get statusLabel {
    if (balanceDue <= 0) return 'Paid';
    if (paidAmount > 0) return 'Partial';
    return 'Unpaid';
  }

  factory BillingRecord.fromJson(Map<String, dynamic> j) => BillingRecord(
        id: j['id'],
        patientId: j['patient_id'] ?? 0,
        patientName: j['patient_name'],
        subtotal: _d(j['subtotal'] ?? j['amount'] ?? 0),
        discount: _d(j['discount'] ?? 0),
        paidAmount: _d(j['paid_amount'] ?? 0),
        creditUsed: _d(j['credit_used'] ?? 0),
        paymentMethod: j['payment_method'],
        paymentDate: j['payment_date'],
        subtotalExpr: j['subtotal_expr']?.toString(),
        discountExpr: j['discount_expr']?.toString(),
        paidAmountExpr: j['paid_amount_expr']?.toString(),
        updatedAt: j['updated_at'],
        isSynced: true,
      );

  factory BillingRecord.fromDb(Map<String, dynamic> row) => BillingRecord(
        id: row['id'],
        patientId: row['patient_id'] ?? 0,
        patientName: row['patient_name'],
        subtotal: _d(row['subtotal'] ?? 0),
        discount: _d(row['discount'] ?? 0),
        paidAmount: _d(row['paid_amount'] ?? 0),
        creditUsed: _d(row['credit_used'] ?? 0),
        paymentMethod: row['payment_method'],
        paymentDate: row['payment_date'],
        subtotalExpr: row['subtotal_expr'] as String?,
        discountExpr: row['discount_expr'] as String?,
        paidAmountExpr: row['paid_amount_expr'] as String?,
        updatedAt: row['updated_at'],
        isSynced: (row['is_synced'] ?? 0) == 1,
      );

  Map<String, dynamic> toDb() => {
        if (id != null) 'id': id,
        'patient_id': patientId,
        'patient_name': patientName,
        'subtotal': subtotal,
        'discount': discount,
        'paid_amount': paidAmount,
        'credit_used': creditUsed,
        'payment_method': paymentMethod,
        'payment_date': paymentDate,
        'subtotal_expr': subtotalExpr,
        'discount_expr': discountExpr,
        'paid_amount_expr': paidAmountExpr,
        'updated_at': updatedAt ?? DateTime.now().toIso8601String(),
        'is_synced': isSynced ? 1 : 0,
      };

  Map<String, dynamic> toJson() => {
        if (id != null) 'id': id,
        'patient_id': patientId,
        'subtotal': subtotal,
        'discount': discount,
        'paid_amount': paidAmount,
        'credit_used': creditUsed,
        if (paymentMethod != null) 'payment_method': paymentMethod,
        if (paymentDate != null) 'payment_date': paymentDate,
      };
}

double _d(dynamic v) {
  if (v is double) return v;
  if (v is int) return v.toDouble();
  return double.tryParse(v?.toString() ?? '0') ?? 0;
}
