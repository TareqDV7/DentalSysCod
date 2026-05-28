class Expense {
  final int? id;
  final String category;
  final double amount;
  final String? expenseDate;
  final String status; // paid | postponed
  final String? vendor;
  final String? notes;
  // Provenance: 'followup' marks an expense auto-created from a follow-up's lab
  // cost (referenceId = the follow-up id), so it can be kept in sync and removed
  // when that follow-up changes. null/'manual' = a hand-entered expense.
  final String? sourceType;
  final int? referenceId;
  final String? updatedAt;
  final bool isSynced;

  Expense({
    this.id,
    required this.category,
    required this.amount,
    this.expenseDate,
    this.status = 'paid',
    this.vendor,
    this.notes,
    this.sourceType,
    this.referenceId,
    this.updatedAt,
    this.isSynced = false,
  });

  bool get isAuto => sourceType == 'followup';

  factory Expense.fromJson(Map<String, dynamic> j) => Expense(
        id: j['id'],
        category: j['category'] ?? '',
        amount: _d(j['amount'] ?? 0),
        expenseDate: j['expense_date'] ?? j['date'],
        status: j['status'] ?? j['payment_status'] ?? 'paid',
        vendor: j['vendor'],
        notes: j['notes'],
        sourceType: j['source_type'],
        referenceId: j['reference_id'] is int
            ? j['reference_id']
            : int.tryParse('${j['reference_id'] ?? ''}'),
        updatedAt: j['updated_at'],
        isSynced: true,
      );

  factory Expense.fromDb(Map<String, dynamic> row) => Expense(
        id: row['id'],
        category: row['category'] ?? '',
        amount: _d(row['amount'] ?? 0),
        expenseDate: row['expense_date'],
        status: row['status'] ?? 'paid',
        vendor: row['vendor'],
        notes: row['notes'],
        sourceType: row['source_type'] as String?,
        referenceId: row['reference_id'] as int?,
        updatedAt: row['updated_at'],
        isSynced: (row['is_synced'] ?? 0) == 1,
      );

  Map<String, dynamic> toDb() => {
        if (id != null) 'id': id,
        'category': category,
        'amount': amount,
        'expense_date': expenseDate,
        'status': status,
        'vendor': vendor,
        'notes': notes,
        'source_type': sourceType,
        'reference_id': referenceId,
        'updated_at': updatedAt ?? DateTime.now().toIso8601String(),
        'is_synced': isSynced ? 1 : 0,
      };

  Map<String, dynamic> toJson() => {
        if (id != null) 'id': id,
        'category': category,
        'amount': amount,
        if (expenseDate != null) 'expense_date': expenseDate,
        'status': status,
        if (vendor != null) 'vendor': vendor,
        if (notes != null) 'notes': notes,
        if (sourceType != null) 'source_type': sourceType,
        if (referenceId != null) 'reference_id': referenceId,
      };

  Expense copyWith({int? id, bool? isSynced, String? updatedAt}) => Expense(
        id: id ?? this.id,
        category: category,
        amount: amount,
        expenseDate: expenseDate,
        status: status,
        vendor: vendor,
        notes: notes,
        sourceType: sourceType,
        referenceId: referenceId,
        updatedAt: updatedAt ?? this.updatedAt,
        isSynced: isSynced ?? this.isSynced,
      );
}

double _d(dynamic v) {
  if (v is double) return v;
  if (v is int) return v.toDouble();
  return double.tryParse(v?.toString() ?? '0') ?? 0;
}
