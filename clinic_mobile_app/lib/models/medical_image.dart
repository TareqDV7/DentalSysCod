/// A patient's medical image (X-ray / photo). Unlike the synced clinical
/// tables this is NOT part of the text-JSON sync envelope — the bytes are
/// large, so images flow through the local server over LAN: each row is
/// uploaded to / pulled from `/api/medical-images` and the bytes are cached
/// on-device at [localPath].
///
/// [serverId] is the desktop `medical_images.id`; null until this device's
/// upload has been accepted (or for a row that only exists locally so far).
class MedicalImage {
  final int? id;
  final int? serverId;
  final int patientId;
  final String fileName;
  final String? localPath;
  final String? uploadedAt;
  final String? notes;
  final bool isSynced;

  MedicalImage({
    this.id,
    this.serverId,
    required this.patientId,
    required this.fileName,
    this.localPath,
    this.uploadedAt,
    this.notes,
    this.isSynced = false,
  });

  factory MedicalImage.fromDb(Map<String, dynamic> row) => MedicalImage(
        id: row['id'] as int?,
        serverId: row['server_id'] as int?,
        patientId: (row['patient_id'] as num).toInt(),
        fileName: (row['file_name'] ?? '').toString(),
        localPath: row['local_path'] as String?,
        uploadedAt: row['uploaded_at'] as String?,
        notes: row['notes'] as String?,
        isSynced: (row['is_synced'] ?? 0) == 1,
      );

  Map<String, dynamic> toDb() => {
        if (id != null) 'id': id,
        'server_id': serverId,
        'patient_id': patientId,
        'file_name': fileName,
        'local_path': localPath,
        'uploaded_at': uploadedAt,
        'notes': notes,
        'is_synced': isSynced ? 1 : 0,
      };

  MedicalImage copyWith({
    int? id,
    int? serverId,
    String? localPath,
    String? uploadedAt,
    String? notes,
    bool? isSynced,
  }) =>
      MedicalImage(
        id: id ?? this.id,
        serverId: serverId ?? this.serverId,
        patientId: patientId,
        fileName: fileName,
        localPath: localPath ?? this.localPath,
        uploadedAt: uploadedAt ?? this.uploadedAt,
        notes: notes ?? this.notes,
        isSynced: isSynced ?? this.isSynced,
      );
}
