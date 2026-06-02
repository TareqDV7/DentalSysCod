/// An editable tooth-condition catalog entry. Mirrors the server's
/// `tooth_conditions` table and the `/api/tooth-conditions` endpoints.
class ToothCondition {
  final int? id;
  final String name;
  final String? nameAr;
  final String color;
  final String? icon;
  final int sortOrder;
  final bool active;
  final String? updatedAt;
  final bool isSynced;

  const ToothCondition({
    this.id,
    required this.name,
    this.nameAr,
    this.color = '#9ca3af',
    this.icon,
    this.sortOrder = 0,
    this.active = true,
    this.updatedAt,
    this.isSynced = false,
  });

  factory ToothCondition.fromJson(Map<String, dynamic> j) => ToothCondition(
        id: j['id'] is int ? j['id'] : int.tryParse('${j['id']}'),
        name: (j['name'] ?? '').toString(),
        nameAr: j['name_ar']?.toString(),
        color: (j['color'] ?? '#9ca3af').toString(),
        icon: j['icon']?.toString(),
        sortOrder:
            (j['sort_order'] is num) ? (j['sort_order'] as num).toInt() : 0,
        active: (j['active'] ?? 1) == 1 || j['active'] == true,
        updatedAt: j['updated_at']?.toString(),
        isSynced: true,
      );

  factory ToothCondition.fromDb(Map<String, dynamic> r) => ToothCondition(
        id: r['id'] as int?,
        name: (r['name'] ?? '').toString(),
        nameAr: r['name_ar'] as String?,
        color: (r['color'] ?? '#9ca3af').toString(),
        icon: r['icon'] as String?,
        sortOrder: (r['sort_order'] ?? 0) as int,
        active: (r['active'] ?? 1) == 1,
        updatedAt: r['updated_at'] as String?,
        isSynced: (r['is_synced'] ?? 0) == 1,
      );

  Map<String, dynamic> toJson() => {
        if (id != null) 'id': id,
        'name': name,
        'name_ar': nameAr,
        'color': color,
        'icon': icon,
        'sort_order': sortOrder,
        'active': active ? 1 : 0,
      };

  Map<String, dynamic> toDb() => {
        if (id != null) 'id': id,
        'name': name,
        'name_ar': nameAr,
        'color': color,
        'icon': icon,
        'sort_order': sortOrder,
        'active': active ? 1 : 0,
        'updated_at': updatedAt ?? DateTime.now().toIso8601String(),
        'is_synced': isSynced ? 1 : 0,
      };

  ToothCondition copyWith({
    int? id,
    String? name,
    String? nameAr,
    String? color,
    String? icon,
    int? sortOrder,
    bool? active,
    String? updatedAt,
    bool? isSynced,
  }) =>
      ToothCondition(
        id: id ?? this.id,
        name: name ?? this.name,
        nameAr: nameAr ?? this.nameAr,
        color: color ?? this.color,
        icon: icon ?? this.icon,
        sortOrder: sortOrder ?? this.sortOrder,
        active: active ?? this.active,
        updatedAt: updatedAt ?? this.updatedAt,
        isSynced: isSynced ?? this.isSynced,
      );
}
