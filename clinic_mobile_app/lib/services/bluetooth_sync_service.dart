import 'dart:async';
import 'dart:convert';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import '../models/patient.dart';
import '../models/appointment.dart';
import '../models/visit.dart';
import '../models/billing_record.dart';
import '../models/expense.dart';
import 'database_service.dart';

/// BLE UUIDs used by the clinic sync protocol.
const _serviceUuid = '4fafc201-1fb5-459e-8fcc-c5c9c331914b';
const _charUuid = 'beb5483e-36e1-4688-b7f5-ea07361b26a8';

enum BluetoothSyncState { idle, scanning, connecting, transferring, done, error }

class BluetoothSyncService {
  final DatabaseService _db;
  BluetoothSyncState _state = BluetoothSyncState.idle;
  String? _lastError;
  final _stateController = StreamController<BluetoothSyncState>.broadcast();

  BluetoothSyncService(this._db);

  Stream<BluetoothSyncState> get stateStream => _stateController.stream;
  BluetoothSyncState get state => _state;
  String? get lastError => _lastError;

  void _emit(BluetoothSyncState s) {
    _state = s;
    _stateController.add(s);
  }

  /// Scan for nearby clinic devices and sync with the first found.
  Future<bool> scanAndSync() async {
    _emit(BluetoothSyncState.scanning);
    _lastError = null;

    try {
      final adapterState = await FlutterBluePlus.adapterState.first;
      if (adapterState != BluetoothAdapterState.on) {
        _lastError = 'Bluetooth is off. Please enable it and try again.';
        _emit(BluetoothSyncState.error);
        return false;
      }

      BluetoothDevice? target;
      final sub = FlutterBluePlus.scanResults.listen((results) {
        for (final r in results) {
          final uuids = r.advertisementData.serviceUuids
              .map((u) => u.toString().toLowerCase())
              .toList();
          if (uuids.contains(_serviceUuid.toLowerCase())) {
            target = r.device;
          }
        }
      });

      await FlutterBluePlus.startScan(
        withServices: [Guid(_serviceUuid)],
        timeout: const Duration(seconds: 10),
      );
      await Future.delayed(const Duration(seconds: 10));
      await sub.cancel();
      await FlutterBluePlus.stopScan();

      if (target == null) {
        _lastError = 'No clinic devices found nearby.';
        _emit(BluetoothSyncState.error);
        return false;
      }

      _emit(BluetoothSyncState.connecting);
      await target!.connect(timeout: const Duration(seconds: 15));

      _emit(BluetoothSyncState.transferring);
      final success = await _exchangeData(target!);
      await target!.disconnect();

      _emit(success ? BluetoothSyncState.done : BluetoothSyncState.error);
      return success;
    } catch (e) {
      _lastError = e.toString();
      _emit(BluetoothSyncState.error);
      return false;
    }
  }

  Future<bool> _exchangeData(BluetoothDevice device) async {
    try {
      final services = await device.discoverServices();
      final service = services
          .where((s) => s.uuid.toString().toLowerCase() == _serviceUuid.toLowerCase())
          .firstOrNull;
      if (service == null) return false;

      final char = service.characteristics
          .where((c) => c.uuid.toString().toLowerCase() == _charUuid.toLowerCase())
          .firstOrNull;
      if (char == null) return false;

      // read remote snapshot
      if (char.properties.read) {
        final rawBytes = await char.read();
        final jsonStr = utf8.decode(rawBytes);
        final remote = jsonDecode(jsonStr) as Map<String, dynamic>;
        await _mergeRemote(remote);
      }

      // write local snapshot
      if (char.properties.write) {
        final local = await _buildLocalSnapshot();
        final bytes = utf8.encode(jsonEncode(local));
        // BLE MTU is small; send in 512-byte chunks
        for (int i = 0; i < bytes.length; i += 512) {
          final chunk = bytes.sublist(
              i, i + 512 > bytes.length ? bytes.length : i + 512);
          await char.write(chunk, withoutResponse: char.properties.writeWithoutResponse);
        }
      }

      await _db.setSyncMeta(
          'last_bt_sync', DateTime.now().toIso8601String());
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<Map<String, dynamic>> _buildLocalSnapshot() async {
    final db = await _db.database;
    return {
      'patients': await db.query('patients'),
      'appointments': await db.query('appointments'),
      'visits': await db.query('visits'),
      'billing_records': await db.query('billing_records'),
      'expenses': await db.query('expenses'),
    };
  }

  Future<void> _mergeRemote(Map<String, dynamic> data) async {
    for (final p in (data['patients'] as List? ?? [])) {
      await _db.upsertPatient(
          Patient.fromDb(Map<String, dynamic>.from(p as Map)));
    }
    for (final a in (data['appointments'] as List? ?? [])) {
      await _db.upsertAppointment(
          Appointment.fromDb(Map<String, dynamic>.from(a as Map)));
    }
    for (final v in (data['visits'] as List? ?? [])) {
      await _db.upsertVisit(
          Visit.fromDb(Map<String, dynamic>.from(v as Map)));
    }
    for (final b in (data['billing_records'] as List? ?? [])) {
      await _db.upsertBillingRecord(
          BillingRecord.fromDb(Map<String, dynamic>.from(b as Map)));
    }
    for (final e in (data['expenses'] as List? ?? [])) {
      await _db.upsertExpense(
          Expense.fromDb(Map<String, dynamic>.from(e as Map)));
    }
  }

  void dispose() => _stateController.close();
}
