/// A row of the per-patient follow-up sheet. Mirrors the server's
/// `patient_followups` table 1:1 (minus the `*_expr` columns, which are a v2
/// item — see docs/superpowers/specs/2026-05-17-mobile-followups-design.md).
class Followup {
  final int? id;
  final int patientId;
  final String followupDate;
  final String treatmentProcedure;
  final int? procedureId;
  final String? toothNo;
  final String? diagnosis;
  final double price;
  final double discount;
  final double labExpense;
  final double payment;
  final double remainingAmount;
  final String? notes;
  final String? updatedAt;
  final bool isSynced;

  Followup({
    this.id,
    required this.patientId,
    required this.followupDate,
    required this.treatmentProcedure,
    this.procedureId,
    this.toothNo,
    this.diagnosis,
    this.price = 0,
    this.discount = 0,
    this.labExpense = 0,
    this.payment = 0,
    this.remainingAmount = 0,
    this.notes,
    this.updatedAt,
    this.isSynced = false,
  });

  double get clinicProfit => price - discount - labExpense;

  factory Followup.fromJson(Map<String, dynamic> j) => Followup(
        id: j['id'] is int ? j['id'] : int.tryParse('${j['id']}'),
        patientId: (j['patient_id'] as num).toInt(),
        followupDate: (j['followup_date'] ?? '').toString(),
        treatmentProcedure: (j['treatment_procedure'] ?? '').toString(),
        procedureId: j['procedure_id'] is int
            ? j['procedure_id']
            : int.tryParse('${j['procedure_id'] ?? ''}'),
        toothNo: j['tooth_no']?.toString(),
        diagnosis: j['diagnosis']?.toString(),
        price: _num(j['price']),
        discount: _num(j['discount']),
        labExpense: _num(j['lab_expense']),
        payment: _num(j['payment']),
        remainingAmount: _num(j['remaining_amount']),
        notes: j['notes']?.toString(),
        updatedAt: j['updated_at']?.toString(),
        isSynced: true,
      );

  factory Followup.fromDb(Map<String, dynamic> row) => Followup(
        id: row['id'],
        patientId: (row['patient_id'] as num).toInt(),
        followupDate: (row['followup_date'] ?? '').toString(),
        treatmentProcedure: (row['treatment_procedure'] ?? '').toString(),
        procedureId: row['procedure_id'] as int?,
        toothNo: row['tooth_no'] as String?,
        diagnosis: row['diagnosis'] as String?,
        price: _num(row['price']),
        discount: _num(row['discount']),
        labExpense: _num(row['lab_expense']),
        payment: _num(row['payment']),
        remainingAmount: _num(row['remaining_amount']),
        notes: row['notes'] as String?,
        updatedAt: row['updated_at'] as String?,
        isSynced: (row['is_synced'] ?? 0) == 1,
      );

  Map<String, dynamic> toDb() => {
        if (id != null) 'id': id,
        'patient_id': patientId,
        'followup_date': followupDate,
        'treatment_procedure': treatmentProcedure,
        'procedure_id': procedureId,
        'tooth_no': toothNo,
        'diagnosis': diagnosis,
        'price': price,
        'discount': discount,
        'lab_expense': labExpense,
        'payment': payment,
        'remaining_amount': remainingAmount,
        'clinic_profit': clinicProfit,
        'notes': notes,
        'updated_at': updatedAt ?? DateTime.now().toIso8601String(),
        'is_synced': isSynced ? 1 : 0,
      };

  Followup copyWith({
    int? id,
    String? followupDate,
    String? treatmentProcedure,
    int? procedureId,
    String? toothNo,
    String? diagnosis,
    double? price,
    double? discount,
    double? labExpense,
    double? payment,
    double? remainingAmount,
    String? notes,
    String? updatedAt,
    bool? isSynced,
  }) =>
      Followup(
        id: id ?? this.id,
        patientId: patientId,
        followupDate: followupDate ?? this.followupDate,
        treatmentProcedure: treatmentProcedure ?? this.treatmentProcedure,
        procedureId: procedureId ?? this.procedureId,
        toothNo: toothNo ?? this.toothNo,
        diagnosis: diagnosis ?? this.diagnosis,
        price: price ?? this.price,
        discount: discount ?? this.discount,
        labExpense: labExpense ?? this.labExpense,
        payment: payment ?? this.payment,
        remainingAmount: remainingAmount ?? this.remainingAmount,
        notes: notes ?? this.notes,
        updatedAt: updatedAt ?? this.updatedAt,
        isSynced: isSynced ?? this.isSynced,
      );

  static double _num(dynamic v) {
    if (v == null) return 0;
    if (v is num) return v.toDouble();
    return double.tryParse(v.toString()) ?? 0;
  }

  /// Port of the server's `_recompute_followup_balances`. Pure function so
  /// the algorithm has unit-test coverage independent of sqflite. Takes a
  /// list of (price, discount, payment) tuples in the same order the server
  /// walks them: `(followup_date ASC, id ASC)`. Returns the cumulative
  /// running balance for each row. **May be negative** — represents patient
  /// credit, same as server.
  static List<double> runningBalances(
      List<({double price, double discount, double payment})> ordered) {
    double running = 0.0;
    final out = <double>[];
    for (final r in ordered) {
      running += r.price - r.discount - r.payment;
      out.add((running * 100).round() / 100);
    }
    return out;
  }
}
