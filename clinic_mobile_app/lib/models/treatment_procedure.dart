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

  factory TreatmentProcedure.fromJson(Map<String, dynamic> j) {
    // Accept both spellings — server uses default_lab_expense / active,
    // older / local rows use lab_expense / is_active.
    final lab = j['default_lab_expense'] ?? j['lab_expense'] ?? 0;
    final activeRaw = j.containsKey('active') ? j['active'] : j['is_active'];
    return TreatmentProcedure(
      id: j['id'],
      name: j['name'] ?? '',
      defaultPrice: _d(j['default_price'] ?? j['price'] ?? 0),
      labExpense: _d(lab),
      requiresLab: j['requires_lab'] == true || j['requires_lab'] == 1,
      isActive: activeRaw == null || (activeRaw != false && activeRaw != 0),
      updatedAt: j['updated_at'],
      isSynced: true,
    );
  }

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

  /// Server payload. Uses the desktop's column names — `default_lab_expense`
  /// + `active` — not the local-DB names (`lab_expense` + `is_active`). The
  /// `fromJson` accepts both for backward compat.
  Map<String, dynamic> toJson() => {
        if (id != null) 'id': id,
        'name': name,
        'default_price': defaultPrice,
        'default_lab_expense': labExpense,
        'requires_lab': requiresLab,
        'active': isActive,
      };

  TreatmentProcedure copyWith({
    int? id,
    String? name,
    double? defaultPrice,
    double? labExpense,
    bool? requiresLab,
    bool? isActive,
    String? updatedAt,
    bool? isSynced,
  }) =>
      TreatmentProcedure(
        id: id ?? this.id,
        name: name ?? this.name,
        defaultPrice: defaultPrice ?? this.defaultPrice,
        labExpense: labExpense ?? this.labExpense,
        requiresLab: requiresLab ?? this.requiresLab,
        isActive: isActive ?? this.isActive,
        updatedAt: updatedAt ?? this.updatedAt,
        isSynced: isSynced ?? this.isSynced,
      );
}

double _d(dynamic v) {
  if (v is double) return v;
  if (v is int) return v.toDouble();
  return double.tryParse(v?.toString() ?? '0') ?? 0;
}
