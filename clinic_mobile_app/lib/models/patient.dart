class Patient {
  final int? id;
  final String firstName;
  final String lastName;
  final String? dateOfBirth;
  final String? phone;
  final String? email;
  final String? address;
  final String? medicalHistory;
  final String? createdAt;
  final String? updatedAt;
  final bool isSynced;

  Patient({
    this.id,
    required this.firstName,
    required this.lastName,
    this.dateOfBirth,
    this.phone,
    this.email,
    this.address,
    this.medicalHistory,
    this.createdAt,
    this.updatedAt,
    this.isSynced = false,
  });

  String get fullName => '$firstName $lastName';

  factory Patient.fromJson(Map<String, dynamic> j) => Patient(
        id: j['id'],
        firstName: j['first_name'] ?? '',
        lastName: j['last_name'] ?? '',
        dateOfBirth: j['date_of_birth'],
        phone: j['phone'],
        email: j['email'],
        address: j['address'],
        medicalHistory: j['medical_history'],
        createdAt: j['created_at'],
        updatedAt: j['updated_at'],
        isSynced: true,
      );

  Map<String, dynamic> toJson() => {
        if (id != null) 'id': id,
        'first_name': firstName,
        'last_name': lastName,
        if (dateOfBirth != null) 'date_of_birth': dateOfBirth,
        if (phone != null) 'phone': phone,
        if (email != null) 'email': email,
        if (address != null) 'address': address,
        if (medicalHistory != null) 'medical_history': medicalHistory,
      };

  factory Patient.fromDb(Map<String, dynamic> row) => Patient(
        id: row['id'],
        firstName: row['first_name'] ?? '',
        lastName: row['last_name'] ?? '',
        dateOfBirth: row['date_of_birth'],
        phone: row['phone'],
        email: row['email'],
        address: row['address'],
        medicalHistory: row['medical_history'],
        createdAt: row['created_at'],
        updatedAt: row['updated_at'],
        isSynced: (row['is_synced'] ?? 0) == 1,
      );

  Map<String, dynamic> toDb() => {
        if (id != null) 'id': id,
        'first_name': firstName,
        'last_name': lastName,
        'date_of_birth': dateOfBirth,
        'phone': phone,
        'email': email,
        'address': address,
        'medical_history': medicalHistory,
        'updated_at': updatedAt ?? DateTime.now().toIso8601String(),
        'is_synced': isSynced ? 1 : 0,
      };

  Patient copyWith({
    int? id,
    String? firstName,
    String? lastName,
    String? dateOfBirth,
    String? phone,
    String? email,
    String? address,
    String? medicalHistory,
    String? updatedAt,
    bool? isSynced,
  }) =>
      Patient(
        id: id ?? this.id,
        firstName: firstName ?? this.firstName,
        lastName: lastName ?? this.lastName,
        dateOfBirth: dateOfBirth ?? this.dateOfBirth,
        phone: phone ?? this.phone,
        email: email ?? this.email,
        address: address ?? this.address,
        medicalHistory: medicalHistory ?? this.medicalHistory,
        createdAt: createdAt,
        updatedAt: updatedAt ?? this.updatedAt,
        isSynced: isSynced ?? this.isSynced,
      );
}
