class Appointment {
  final int? id;
  final int patientId;
  final String? patientName;
  final String appointmentDatetime;
  final int? durationMinutes;
  final String? treatmentType;
  final String status; // scheduled | completed | postponed | pending
  final String? notes;
  final String? updatedAt;
  final bool isSynced;
  final int? dentistId;

  Appointment({
    this.id,
    required this.patientId,
    this.patientName,
    required this.appointmentDatetime,
    this.durationMinutes,
    this.treatmentType,
    this.status = 'scheduled',
    this.notes,
    this.updatedAt,
    this.isSynced = false,
    this.dentistId,
  });

  DateTime get dateTime =>
      DateTime.tryParse(appointmentDatetime) ??
      DateTime.tryParse(appointmentDatetime.replaceFirst(' ', 'T')) ??
      DateTime.now();

  factory Appointment.fromJson(Map<String, dynamic> j) => Appointment(
        id: j['id'],
        patientId: j['patient_id'] ?? 0,
        patientName: j['patient_name'],
        appointmentDatetime: j['appointment_datetime'] ??
            j['appointment_date'] ??
            j['date_time'] ??
            '',
        durationMinutes: j['duration_minutes'] ?? j['duration'],
        treatmentType: j['treatment_type'],
        status: j['status'] ?? 'scheduled',
        notes: j['notes'],
        updatedAt: j['updated_at'],
        isSynced: true,
        dentistId: j['dentist_id'],
      );

  Map<String, dynamic> toJson() => {
        if (id != null) 'id': id,
        'patient_id': patientId,
      'appointment_date': appointmentDatetime,
        'appointment_datetime': appointmentDatetime,
      if (durationMinutes != null) 'duration': durationMinutes,
        if (durationMinutes != null) 'duration_minutes': durationMinutes,
        if (treatmentType != null) 'treatment_type': treatmentType,
        'status': status,
        if (notes != null) 'notes': notes,
        if (dentistId != null) 'dentist_id': dentistId,
      };

  factory Appointment.fromDb(Map<String, dynamic> row) => Appointment(
        id: row['id'],
        patientId: row['patient_id'] ?? 0,
        patientName: row['patient_name'],
        appointmentDatetime:
          row['appointment_datetime'] ?? row['appointment_date'] ?? '',
        durationMinutes: row['duration_minutes'],
        treatmentType: row['treatment_type'],
        status: row['status'] ?? 'scheduled',
        notes: row['notes'],
        updatedAt: row['updated_at'],
        isSynced: (row['is_synced'] ?? 0) == 1,
        dentistId: row['dentist_id'],
      );

  Map<String, dynamic> toDb() => {
        if (id != null) 'id': id,
        'patient_id': patientId,
        'patient_name': patientName,
        'appointment_datetime': appointmentDatetime,
        'duration_minutes': durationMinutes,
        'treatment_type': treatmentType,
        'status': status,
        'notes': notes,
        'updated_at': updatedAt ?? DateTime.now().toIso8601String(),
        'is_synced': isSynced ? 1 : 0,
        'dentist_id': dentistId,
      };

  Appointment copyWith({String? status, bool? isSynced, int? dentistId}) => Appointment(
        id: id,
        patientId: patientId,
        patientName: patientName,
        appointmentDatetime: appointmentDatetime,
        durationMinutes: durationMinutes,
        treatmentType: treatmentType,
        status: status ?? this.status,
        notes: notes,
        updatedAt: DateTime.now().toIso8601String(),
        isSynced: isSynced ?? this.isSynced,
        dentistId: dentistId ?? this.dentistId,
      );
}
