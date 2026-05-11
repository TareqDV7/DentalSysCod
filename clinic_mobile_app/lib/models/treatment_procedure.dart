class TreatmentProcedure {
  final int? id;
  final String name;
  final double defaultPrice;
  final double labExpense;
  final bool requiresLab;
  final bool isActive;
  final String? updatedAt;
  final bool isSynced;

  TreatmentProcedure({
    this.id,
    required this.name,
    this.defaultPrice = 0,
    this.labExpense = 0,
    this.requiresLab = false,
    this.isActive = true,
    this.updatedAt,
    this.isSynced = false,
  });

  factory TreatmentProcedure.fromJson(Map<String, dynamic> j) =>
      TreatmentProcedure(
        id: j['id'],
        name: j['name'] ?? '',
        defaultPrice: _d(j['default_price'] ?? j['price'] ?? 0),
        labExpense: _d(j['lab_expense'] ?? 0),
        requiresLab: j['requires_lab'] == true || j['requires_lab'] == 1,
        isActive: j['is_active'] != false && j['is_active'] != 0,
        updatedAt: j['updated_at'],
        isSynced: true,
      );

  factory TreatmentProcedure.fromDb(Map<String, dynamic> row) =>
      TreatmentProcedure(
        id: row['id'],
        name: row['name'] ?? '',
        defaultPrice: _d(row['default_price'] ?? 0),
        labExpense: _d(row['lab_expense'] ?? 0),
        requiresLab: (row['requires_lab'] ?? 0) == 1,
        isActive: (row['is_active'] ?? 1) == 1,
        updatedAt: row['updated_at'],
        isSynced: (row['is_synced'] ?? 0) == 1,
      );

  Map<String, dynamic> toDb() => {
        if (id != null) 'id': id,
        'name': name,
        'default_price': defaultPrice,
        'lab_expense': labExpense,
        'requires_lab': requiresLab ? 1 : 0,
        'is_active': isActive ? 1 : 0,
        'updated_at': updatedAt ?? DateTime.now().toIso8601String(),
        'is_synced': isSynced ? 1 : 0,
      };
}

double _d(dynamic v) {
  if (v is double) return v;
  if (v is int) return v.toDouble();
  return double.tryParse(v?.toString() ?? '0') ?? 0;
}
