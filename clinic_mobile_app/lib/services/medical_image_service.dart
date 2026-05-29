import 'dart:io';
import 'dart:typed_data';

import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import '../models/medical_image.dart';
import 'clinic_api.dart';
import 'database_service.dart';

/// Syncs patient medical images (X-rays / photos) through the local clinic
/// server over LAN. The bytes are too large for the text-JSON / Bluetooth
/// sync envelope and the cloud node blocks the image endpoints, so this runs
/// only when the active link is local Wi-Fi — exactly the desktop's own
/// "uploads are network-local" model, made bidirectional desktop↔mobile.
///
/// Pending uploads and undownloaded server rows simply wait until a LAN
/// connection is available again; nothing is lost offline.
class MedicalImageService {
  final DatabaseService _db;
  final ClinicApi _api;

  MedicalImageService(this._db, this._api);

  static const _endpoint = '/api/medical-images';

  Future<List<MedicalImage>> getForPatient(int patientId) =>
      _db.getMedicalImages(patientId);

  /// True when the current link can carry image bytes (LAN to the local
  /// server). Cloud blocks the endpoints; BT can't carry binaries.
  bool get _canTransfer => _api.link == SyncLink.localWifi;

  Future<Directory> _imagesDir() async {
    final base = await getApplicationDocumentsDirectory();
    final dir = Directory(p.join(base.path, 'medical_images'));
    if (!await dir.exists()) await dir.create(recursive: true);
    return dir;
  }

  static String _sanitize(String name) =>
      name.replaceAll(RegExp(r'[\\/:*?"<>|]'), '_');

  /// Capture/import a picked file: copy its bytes into app storage, record a
  /// pending local row, then try to upload immediately (best-effort).
  Future<MedicalImage> addFromFile(
    int patientId,
    String sourcePath, {
    String? notes,
  }) async {
    final dir = await _imagesDir();
    final fileName = _sanitize(p.basename(sourcePath));
    final dest = p.join(
        dir.path, '${DateTime.now().millisecondsSinceEpoch}_$fileName');
    await File(sourcePath).copy(dest);

    final row = MedicalImage(
      patientId: patientId,
      fileName: fileName,
      localPath: dest,
      uploadedAt: DateTime.now().toIso8601String(),
      notes: notes,
      isSynced: false,
    );
    final localId = await _db.upsertMedicalImage(row);
    final stored = row.copyWith(id: localId);
    if (_canTransfer) {
      try {
        await _uploadOne(stored);
      } catch (_) {/* stays pending; re-tried on next LAN sync */}
    }
    return stored;
  }

  Future<void> _uploadOne(MedicalImage img) async {
    if (img.localPath == null || img.id == null) return;
    final res = await _api.postMultipart(
      _endpoint,
      fields: {
        'patient_id': '${img.patientId}',
        if ((img.notes ?? '').isNotEmpty) 'notes': img.notes!,
      },
      fileField: 'image',
      filePath: img.localPath!,
      fileName: img.fileName,
    );
    final serverId = res['id'] is int
        ? res['id'] as int
        : int.tryParse('${res['id']}');
    await _db.upsertMedicalImage(
        img.copyWith(serverId: serverId, isSynced: true));
  }

  /// Push every still-pending local image for this patient.
  Future<void> uploadPending(int patientId) async {
    if (!_canTransfer) return;
    final rows = await _db.getMedicalImages(patientId);
    for (final img in rows) {
      if (!img.isSynced && img.localPath != null) {
        try {
          await _uploadOne(img);
        } catch (_) {/* leave pending */}
      }
    }
  }

  /// Pull any server images this device doesn't have yet, caching the bytes.
  Future<void> pullFromServer(int patientId) async {
    if (!_canTransfer) return;
    final listing = await _api.getList(_endpoint, query: {'patient_id': patientId});
    final have = await _db.medicalImageServerIds(patientId);
    final toFetch = missingServerImages(have, listing);
    if (toFetch.isEmpty) return;
    final dir = await _imagesDir();
    for (final row in toFetch) {
      final serverId = row['id'] as int;
      final fileName = _sanitize((row['file_name'] ?? 'image').toString());
      try {
        final bytes = await _api.getBytes('$_endpoint/$serverId/file');
        if (bytes.isEmpty) continue;
        final dest = p.join(dir.path, 'srv_${serverId}_$fileName');
        await File(dest).writeAsBytes(Uint8List.fromList(bytes), flush: true);
        await _db.upsertMedicalImage(MedicalImage(
          serverId: serverId,
          patientId: patientId,
          fileName: (row['file_name'] ?? fileName).toString(),
          localPath: dest,
          uploadedAt: row['uploaded_at']?.toString(),
          notes: row['notes']?.toString(),
          isSynced: true,
        ));
      } catch (_) {/* skip this one; retried next pull */}
    }
  }

  /// One full image sync pass for a patient (LAN-gated): push then pull.
  Future<void> sync(int patientId) async {
    if (!_canTransfer) return;
    await uploadPending(patientId);
    await pullFromServer(patientId);
  }

  Future<void> delete(MedicalImage img) async {
    if (img.id != null) await _db.deleteMedicalImage(img.id!);
    final path = img.localPath;
    if (path != null) {
      try {
        final f = File(path);
        if (await f.exists()) await f.delete();
      } catch (_) {/* file already gone */}
    }
  }

  /// Pure reconciliation: which server-catalog rows are not yet present
  /// locally (by server id). Extracted so it can be unit-tested without the
  /// network/DB.
  static List<Map<String, dynamic>> missingServerImages(
    Set<int> localServerIds,
    List<dynamic> serverListing,
  ) {
    final out = <Map<String, dynamic>>[];
    for (final raw in serverListing) {
      if (raw is! Map) continue;
      final row = Map<String, dynamic>.from(raw);
      final id = row['id'];
      final sid = id is int ? id : int.tryParse('$id');
      if (sid == null) continue;
      if (!localServerIds.contains(sid)) {
        row['id'] = sid;
        out.add(row);
      }
    }
    return out;
  }
}
