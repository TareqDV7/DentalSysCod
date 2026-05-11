import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart';
import '../models/patient.dart';
import '../models/appointment.dart';
import '../models/visit.dart';
import '../models/billing_record.dart';
import '../models/expense.dart';
import '../models/treatment_procedure.dart';

class DatabaseService {
  static DatabaseService? _instance;
  static Database? _db;

  DatabaseService._();
  static DatabaseService get instance => _instance ??= DatabaseService._();

  Future<Database> get database async => _db ??= await _open();

  Future<Database> _open() async {
    final path = join(await getDatabasesPath(), 'clinic_local.db');
    return openDatabase(path, version: 1, onCreate: _onCreate);
  }

  Future<void> _onCreate(Database db, int version) async {
    await db.execute('''
      CREATE TABLE patients (
        id INTEGER PRIMARY KEY,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        date_of_birth TEXT,
        phone TEXT,
        email TEXT,
        address TEXT,
        medical_history TEXT,
        created_at TEXT,
        updated_at TEXT,
        is_synced INTEGER DEFAULT 0
      )
    ''');

    await db.execute('''
      CREATE TABLE appointments (
        id INTEGER PRIMARY KEY,
        patient_id INTEGER NOT NULL,
        patient_name TEXT,
        appointment_datetime TEXT NOT NULL,
        duration_minutes INTEGER,
        treatment_type TEXT,
        status TEXT DEFAULT 'scheduled',
        notes TEXT,
        updated_at TEXT,
        is_synced INTEGER DEFAULT 0
      )
    ''');

    await db.execute('''
      CREATE TABLE visits (
        id INTEGER PRIMARY KEY,
        patient_id INTEGER NOT NULL,
        patient_name TEXT,
        visit_date TEXT NOT NULL,
        procedure_name TEXT,
        price REAL,
        lab_expense REAL,
        payment REAL,
        notes TEXT,
        updated_at TEXT,
        is_synced INTEGER DEFAULT 0
      )
    ''');

    await db.execute('''
      CREATE TABLE billing_records (
        id INTEGER PRIMARY KEY,
        patient_id INTEGER NOT NULL,
        patient_name TEXT,
        subtotal REAL NOT NULL,
        discount REAL DEFAULT 0,
        paid_amount REAL NOT NULL,
        payment_method TEXT,
        payment_date TEXT,
        updated_at TEXT,
        is_synced INTEGER DEFAULT 0
      )
    ''');

    await db.execute('''
      CREATE TABLE expenses (
        id INTEGER PRIMARY KEY,
        category TEXT NOT NULL,
        amount REAL NOT NULL,
        expense_date TEXT,
        status TEXT DEFAULT 'paid',
        vendor TEXT,
        notes TEXT,
        updated_at TEXT,
        is_synced INTEGER DEFAULT 0
      )
    ''');

    await db.execute('''
      CREATE TABLE treatment_procedures (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        default_price REAL DEFAULT 0,
        lab_expense REAL DEFAULT 0,
        requires_lab INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1,
        updated_at TEXT,
        is_synced INTEGER DEFAULT 0
      )
    ''');

    await db.execute('''
      CREATE TABLE sync_meta (
        key TEXT PRIMARY KEY,
        value TEXT
      )
    ''');
  }

  // ── Patients ──────────────────────────────────────────────────────────────

  Future<List<Patient>> getPatients({String? query}) async {
    final db = await database;
    List<Map<String, dynamic>> rows;
    if (query != null && query.isNotEmpty) {
      final q = '%$query%';
      rows = await db.query('patients',
          where:
              'first_name LIKE ? OR last_name LIKE ? OR phone LIKE ? OR email LIKE ?',
          whereArgs: [q, q, q, q],
          orderBy: 'first_name ASC');
    } else {
      rows = await db.query('patients', orderBy: 'first_name ASC');
    }
    return rows.map(Patient.fromDb).toList();
  }

  Future<Patient?> getPatient(int id) async {
    final db = await database;
    final rows =
        await db.query('patients', where: 'id = ?', whereArgs: [id], limit: 1);
    return rows.isEmpty ? null : Patient.fromDb(rows.first);
  }

  Future<int> upsertPatient(Patient p) async {
    final db = await database;
    final data = p.toDb();
    if (p.id != null) {
      final exists = await db.query('patients',
          where: 'id = ?', whereArgs: [p.id], limit: 1);
      if (exists.isNotEmpty) {
        await db
            .update('patients', data, where: 'id = ?', whereArgs: [p.id]);
        return p.id!;
      }
    }
    return db.insert('patients', data,
        conflictAlgorithm: ConflictAlgorithm.replace);
  }

  Future<void> deletePatient(int id) async {
    final db = await database;
    await db.delete('patients', where: 'id = ?', whereArgs: [id]);
  }

  // ── Appointments ──────────────────────────────────────────────────────────

  Future<List<Appointment>> getAppointments({DateTime? date}) async {
    final db = await database;
    List<Map<String, dynamic>> rows;
    if (date != null) {
      final day = date.toIso8601String().substring(0, 10);
      rows = await db.query('appointments',
          where: 'appointment_datetime LIKE ?',
          whereArgs: ['$day%'],
          orderBy: 'appointment_datetime ASC');
    } else {
      rows = await db.query('appointments',
          orderBy: 'appointment_datetime DESC');
    }
    return rows.map(Appointment.fromDb).toList();
  }

  Future<List<Appointment>> getRecentAppointments({int limit = 10}) async {
    final db = await database;
    final rows = await db.query('appointments',
        orderBy: 'appointment_datetime DESC', limit: limit);
    return rows.map(Appointment.fromDb).toList();
  }

  Future<List<Appointment>> getPatientAppointments(int patientId) async {
    final db = await database;
    final rows = await db.query('appointments',
        where: 'patient_id = ?',
        whereArgs: [patientId],
        orderBy: 'appointment_datetime DESC');
    return rows.map(Appointment.fromDb).toList();
  }

  Future<Map<DateTime, int>> getAppointmentCountsByMonth(
      int year, int month) async {
    final db = await database;
    final prefix = '${year.toString().padLeft(4, '0')}-${month.toString().padLeft(2, '0')}';
    final rows = await db.query('appointments',
        where: 'appointment_datetime LIKE ?', whereArgs: ['$prefix%']);
    final Map<DateTime, int> counts = {};
    for (final row in rows) {
      final dt = DateTime.tryParse(row['appointment_datetime'] as String? ?? '');
      if (dt != null) {
        final key = DateTime(dt.year, dt.month, dt.day);
        counts[key] = (counts[key] ?? 0) + 1;
      }
    }
    return counts;
  }

  Future<int> upsertAppointment(Appointment a) async {
    final db = await database;
    final data = a.toDb();
    if (a.id != null) {
      final exists = await db.query('appointments',
          where: 'id = ?', whereArgs: [a.id], limit: 1);
      if (exists.isNotEmpty) {
        await db.update('appointments', data,
            where: 'id = ?', whereArgs: [a.id]);
        return a.id!;
      }
    }
    return db.insert('appointments', data,
        conflictAlgorithm: ConflictAlgorithm.replace);
  }

  Future<void> deleteAppointment(int id) async {
    final db = await database;
    await db.delete('appointments', where: 'id = ?', whereArgs: [id]);
  }

  // ── Visits ────────────────────────────────────────────────────────────────

  Future<List<Visit>> getPatientVisits(int patientId) async {
    final db = await database;
    final rows = await db.query('visits',
        where: 'patient_id = ?',
        whereArgs: [patientId],
        orderBy: 'visit_date DESC');
    return rows.map(Visit.fromDb).toList();
  }

  Future<int> upsertVisit(Visit v) async {
    final db = await database;
    final data = v.toDb();
    if (v.id != null) {
      final exists = await db
          .query('visits', where: 'id = ?', whereArgs: [v.id], limit: 1);
      if (exists.isNotEmpty) {
        await db.update('visits', data, where: 'id = ?', whereArgs: [v.id]);
        return v.id!;
      }
    }
    return db.insert('visits', data,
        conflictAlgorithm: ConflictAlgorithm.replace);
  }

  Future<void> deleteVisit(int id) async {
    final db = await database;
    await db.delete('visits', where: 'id = ?', whereArgs: [id]);
  }

  // ── Billing ───────────────────────────────────────────────────────────────

  Future<List<BillingRecord>> getBillingRecords({int? patientId}) async {
    final db = await database;
    List<Map<String, dynamic>> rows;
    if (patientId != null) {
      rows = await db.query('billing_records',
          where: 'patient_id = ?',
          whereArgs: [patientId],
          orderBy: 'payment_date DESC');
    } else {
      rows = await db.query('billing_records', orderBy: 'payment_date DESC');
    }
    return rows.map(BillingRecord.fromDb).toList();
  }

  Future<int> upsertBillingRecord(BillingRecord b) async {
    final db = await database;
    final data = b.toDb();
    if (b.id != null) {
      final exists = await db.query('billing_records',
          where: 'id = ?', whereArgs: [b.id], limit: 1);
      if (exists.isNotEmpty) {
        await db.update('billing_records', data,
            where: 'id = ?', whereArgs: [b.id]);
        return b.id!;
      }
    }
    return db.insert('billing_records', data,
        conflictAlgorithm: ConflictAlgorithm.replace);
  }

  // ── Expenses ──────────────────────────────────────────────────────────────

  Future<List<Expense>> getExpenses({String? period, String? status}) async {
    final db = await database;
    String? where;
    List<dynamic> args = [];

    if (status != null && status != 'all') {
      where = 'status = ?';
      args.add(status);
    }

    if (period != null && period != 'all') {
      final now = DateTime.now();
      String? from;
      if (period == 'today') {
        from = now.toIso8601String().substring(0, 10);
      } else if (period == 'week') {
        from = now
            .subtract(Duration(days: now.weekday - 1))
            .toIso8601String()
            .substring(0, 10);
      } else if (period == 'month') {
        from =
            '${now.year}-${now.month.toString().padLeft(2, '0')}-01';
      }
      if (from != null) {
        where = where == null
            ? 'expense_date >= ?'
            : '$where AND expense_date >= ?';
        args.add(from);
      }
    }

    final rows = await db.query('expenses',
        where: where,
        whereArgs: args.isEmpty ? null : args,
        orderBy: 'expense_date DESC');
    return rows.map(Expense.fromDb).toList();
  }

  Future<int> upsertExpense(Expense e) async {
    final db = await database;
    final data = e.toDb();
    if (e.id != null) {
      final exists = await db.query('expenses',
          where: 'id = ?', whereArgs: [e.id], limit: 1);
      if (exists.isNotEmpty) {
        await db.update('expenses', data, where: 'id = ?', whereArgs: [e.id]);
        return e.id!;
      }
    }
    return db.insert('expenses', data,
        conflictAlgorithm: ConflictAlgorithm.replace);
  }

  Future<void> deleteExpense(int id) async {
    final db = await database;
    await db.delete('expenses', where: 'id = ?', whereArgs: [id]);
  }

  // ── Treatment Procedures ──────────────────────────────────────────────────

  Future<List<TreatmentProcedure>> getProcedures() async {
    final db = await database;
    final rows = await db.query('treatment_procedures',
        where: 'is_active = 1', orderBy: 'name ASC');
    return rows.map(TreatmentProcedure.fromDb).toList();
  }

  Future<int> upsertProcedure(TreatmentProcedure p) async {
    final db = await database;
    final data = p.toDb();
    return db.insert('treatment_procedures', data,
        conflictAlgorithm: ConflictAlgorithm.replace);
  }

  // ── Stats ─────────────────────────────────────────────────────────────────

  Future<Map<String, dynamic>> getStats() async {
    final db = await database;
    final patientCount =
        Sqflite.firstIntValue(await db.rawQuery('SELECT COUNT(*) FROM patients')) ?? 0;
    final today = DateTime.now().toIso8601String().substring(0, 10);
    final todayAppts = Sqflite.firstIntValue(await db.rawQuery(
            'SELECT COUNT(*) FROM appointments WHERE appointment_datetime LIKE ?',
            ['$today%'])) ??
        0;
    return {'total_patients': patientCount, 'today_appointments': todayAppts};
  }

  // ── Receivables ───────────────────────────────────────────────────────────

  Future<List<Map<String, dynamic>>> getReceivables() async {
    final db = await database;
    final rows = await db.rawQuery('''
      SELECT
        p.id,
        p.first_name || ' ' || p.last_name AS patient_name,
        COALESCE(SUM(b.subtotal - b.discount), 0) AS total,
        COALESCE(SUM(b.paid_amount), 0) AS paid,
        COALESCE(SUM(b.subtotal - b.discount - b.paid_amount), 0) AS balance,
        MAX(b.payment_date) AS last_date
      FROM patients p
      LEFT JOIN billing_records b ON b.patient_id = p.id
      GROUP BY p.id
      HAVING balance > 0
      ORDER BY balance DESC
    ''');
    return rows.toList();
  }

  // ── Sync helpers ──────────────────────────────────────────────────────────

  Future<List<Map<String, dynamic>>> getUnsyncedRows(String table) async {
    final db = await database;
    return db.query(table, where: 'is_synced = 0');
  }

  Future<void> markSynced(String table, int id) async {
    final db = await database;
    await db.update(table, {'is_synced': 1},
        where: 'id = ?', whereArgs: [id]);
  }

  Future<String?> getSyncMeta(String key) async {
    final db = await database;
    final rows = await db
        .query('sync_meta', where: 'key = ?', whereArgs: [key], limit: 1);
    return rows.isEmpty ? null : rows.first['value'] as String?;
  }

  Future<void> setSyncMeta(String key, String value) async {
    final db = await database;
    await db.insert('sync_meta', {'key': key, 'value': value},
        conflictAlgorithm: ConflictAlgorithm.replace);
  }
}
