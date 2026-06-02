/// A multi-visit treatment plan for a patient. Mirrors the server's
/// `treatment_plans` table.
class TreatmentPlan {
  final int? id;
  final int patientId;
  final String planName;
  final String? goals;
  final double estimatedCost;
  final String status;
  final String? startDate;
  final String? endDate;
  final String? notes;
  final String? updatedAt;
  final bool isSynced;
  final List<String> teeth;

  TreatmentPlan({
    this.id,
    required this.patientId,
    required this.planName,
    this.goals,
    this.estimatedCost = 0,
    this.status = 'draft',
    this.startDate,
    this.endDate,
    this.notes,
    this.updatedAt,
    this.isSynced = false,
    this.teeth = const [],
  });

  factory TreatmentPlan.fromJson(Map<String, dynamic> j) => TreatmentPlan(
        id: j['id'] is int ? j['id'] : int.tryParse('${j['id']}'),
        patientId: (j['patient_id'] as num).toInt(),
        planName: (j['plan_name'] ?? '').toString(),
        goals: j['goals']?.toString(),
        estimatedCost: _num(j['estimated_cost']),
        status: (j['status'] ?? 'draft').toString(),
        startDate: j['start_date']?.toString(),
        endDate: j['end_date']?.toString(),
        notes: j['notes']?.toString(),
        updatedAt: j['updated_at']?.toString(),
        isSynced: true,
        teeth: (j['teeth'] as List?)?.map((e) => e.toString()).toList() ??
            const [],
      );

  factory TreatmentPlan.fromDb(Map<String, dynamic> row) => TreatmentPlan(
        id: row['id'] as int?,
        patientId: (row['patient_id'] as num).toInt(),
        planName: (row['plan_name'] ?? '').toString(),
        goals: row['goals'] as String?,
        estimatedCost: _num(row['estimated_cost']),
        status: (row['status'] ?? 'draft').toString(),
        startDate: row['start_date'] as String?,
        endDate: row['end_date'] as String?,
        notes: row['notes'] as String?,
        updatedAt: row['updated_at'] as String?,
        isSynced: (row['is_synced'] ?? 0) == 1,
        teeth: const [], // link rows live in treatment_plan_teeth; fetched via chart API
      );

  Map<String, dynamic> toJson() => {
        if (id != null) 'id': id,
        'patient_id': patientId,
        'plan_name': planName,
        'goals': goals,
        'estimated_cost': estimatedCost,
        'status': status,
        'start_date': startDate,
        'end_date': endDate,
        'notes': notes,
        'teeth': teeth,
      };

  Map<String, dynamic> toDb() => {
        if (id != null) 'id': id,
        'patient_id': patientId,
        'plan_name': planName,
        'goals': goals,
        'estimated_cost': estimatedCost,
        'status': status,
        'start_date': startDate,
        'end_date': endDate,
        'notes': notes,
        'updated_at': updatedAt ?? DateTime.now().toIso8601String(),
        'is_synced': isSynced ? 1 : 0,
      };

  TreatmentPlan copyWith({
    int? id,
    String? planName,
    String? goals,
    double? estimatedCost,
    String? status,
    String? startDate,
    String? endDate,
    String? notes,
    String? updatedAt,
    bool? isSynced,
    List<String>? teeth,
  }) =>
      TreatmentPlan(
        id: id ?? this.id,
        patientId: patientId,
        planName: planName ?? this.planName,
        goals: goals ?? this.goals,
        estimatedCost: estimatedCost ?? this.estimatedCost,
        status: status ?? this.status,
        startDate: startDate ?? this.startDate,
        endDate: endDate ?? this.endDate,
        notes: notes ?? this.notes,
        updatedAt: updatedAt ?? this.updatedAt,
        isSynced: isSynced ?? this.isSynced,
        teeth: teeth ?? this.teeth,
      );

  static double _num(dynamic v) {
    if (v == null) return 0;
    if (v is num) return v.toDouble();
    return double.tryParse(v.toString()) ?? 0;
  }
}
