class Visit {
  final int? id;
  final int patientId;
  final String? patientName;
  final String visitDate;
  final String? procedureName;
  final double? price;
  final double? labExpense;
  final double? payment;
  final String? notes;
  final String? updatedAt;
  final bool isSynced;

  Visit({
    this.id,
    required this.patientId,
    this.patientName,
    required this.visitDate,
    this.procedureName,
    this.price,
    this.labExpense,
    this.payment,
    this.notes,
    this.updatedAt,
    this.isSynced = false,
  });

  double get balance => (price ?? 0) - (payment ?? 0);

  factory Visit.fromJson(Map<String, dynamic> j) => Visit(
        id: j['id'],
        patientId: j['patient_id'] ?? 0,
        patientName: j['patient_name'],
        visitDate: j['visit_date'] ?? j['date'] ?? '',
        procedureName: j['procedure_name'] ?? j['treatment_type'],
        price: _toDouble(j['price']),
        labExpense: _toDouble(j['lab_expense']),
        payment: _toDouble(j['payment']),
        notes: j['notes'],
        updatedAt: j['updated_at'],
        isSynced: true,
      );

  factory Visit.fromDb(Map<String, dynamic> row) => Visit(
        id: row['id'],
        patientId: row['patient_id'] ?? 0,
        patientName: row['patient_name'],
        visitDate: row['visit_date'] ?? '',
        procedureName: row['procedure_name'],
        price: _toDouble(row['price']),
        labExpense: _toDouble(row['lab_expense']),
        payment: _toDouble(row['payment']),
        notes: row['notes'],
        updatedAt: row['updated_at'],
        isSynced: (row['is_synced'] ?? 0) == 1,
      );

  Map<String, dynamic> toDb() => {
        if (id != null) 'id': id,
        'patient_id': patientId,
        'patient_name': patientName,
        'visit_date': visitDate,
        'procedure_name': procedureName,
        'price': price,
        'lab_expense': labExpense,
        'payment': payment,
        'notes': notes,
        'updated_at': updatedAt ?? DateTime.now().toIso8601String(),
        'is_synced': isSynced ? 1 : 0,
      };

  Map<String, dynamic> toJson() => {
        if (id != null) 'id': id,
        'patient_id': patientId,
        'visit_date': visitDate,
        if (procedureName != null) 'procedure_name': procedureName,
        if (price != null) 'price': price,
        if (labExpense != null) 'lab_expense': labExpense,
        if (payment != null) 'payment': payment,
        if (notes != null) 'notes': notes,
      };

  Visit copyWith({
    int? id,
    int? patientId,
    String? patientName,
    String? visitDate,
    String? procedureName,
    double? price,
    double? labExpense,
    double? payment,
    String? notes,
    String? updatedAt,
    bool? isSynced,
  }) =>
      Visit(
        id: id ?? this.id,
        patientId: patientId ?? this.patientId,
        patientName: patientName ?? this.patientName,
        visitDate: visitDate ?? this.visitDate,
        procedureName: procedureName ?? this.procedureName,
        price: price ?? this.price,
        labExpense: labExpense ?? this.labExpense,
        payment: payment ?? this.payment,
        notes: notes ?? this.notes,
        updatedAt: updatedAt ?? this.updatedAt,
        isSynced: isSynced ?? this.isSynced,
      );
}

double? _toDouble(dynamic v) {
  if (v == null) return null;
  if (v is double) return v;
  if (v is int) return v.toDouble();
  return double.tryParse(v.toString());
}
