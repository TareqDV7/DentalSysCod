/// Clinic-wide non-working day. Mirrors the server's `holidays` table.
class Holiday {
  final int? id;
  final String holidayDate;
  final String? name;
  final String? notes;
  final String? updatedAt;
  final bool isSynced;

  Holiday({
    this.id,
    required this.holidayDate,
    this.name,
    this.notes,
    this.updatedAt,
    this.isSynced = false,
  });

  factory Holiday.fromJson(Map<String, dynamic> j) => Holiday(
        id: j['id'] is int ? j['id'] : int.tryParse('${j['id']}'),
        holidayDate: (j['holiday_date'] ?? '').toString(),
        name: j['name']?.toString(),
        notes: j['notes']?.toString(),
        updatedAt: j['updated_at']?.toString(),
        isSynced: true,
      );

  factory Holiday.fromDb(Map<String, dynamic> row) => Holiday(
        id: row['id'],
        holidayDate: (row['holiday_date'] ?? '').toString(),
        name: row['name'] as String?,
        notes: row['notes'] as String?,
        updatedAt: row['updated_at'] as String?,
        isSynced: (row['is_synced'] ?? 0) == 1,
      );

  Map<String, dynamic> toDb() => {
        if (id != null) 'id': id,
        'holiday_date': holidayDate,
        'name': name,
        'notes': notes,
        'updated_at': updatedAt ?? DateTime.now().toIso8601String(),
        'is_synced': isSynced ? 1 : 0,
      };

  Holiday copyWith({
    int? id,
    String? holidayDate,
    String? name,
    String? notes,
    String? updatedAt,
    bool? isSynced,
  }) =>
      Holiday(
        id: id ?? this.id,
        holidayDate: holidayDate ?? this.holidayDate,
        name: name ?? this.name,
        notes: notes ?? this.notes,
        updatedAt: updatedAt ?? this.updatedAt,
        isSynced: isSynced ?? this.isSynced,
      );
}
