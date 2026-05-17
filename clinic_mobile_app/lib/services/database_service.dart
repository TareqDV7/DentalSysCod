import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart';
import '../models/patient.dart';
import '../models/appointment.dart';
import '../models/visit.dart';
import '../models/billing_record.dart';
import '../models/expense.dart';
import '../models/followup.dart';
import '../models/holiday.dart';
import '../models/treatment_plan.dart';
import '../models/treatment_procedure.dart';

class DatabaseService {
  static DatabaseService? _instance;
  static Database? _db;

  DatabaseService._();
  static DatabaseService get instance => _instance ??= DatabaseService._();

  Future<Database> get database async => _db ??= await _open();

  Future<Database> _open() async {
    final path = join(await getDatabasesPath(), 'clinic_local.db');
    return openDatabase(path,
        version: 4, onCreate: _onCreate, onUpgrade: _onUpgrade);
  }

  /// Maps a local table name to the server-side ("remote") table name it syncs to.
  static const Map<String, String> localToRemoteTable = {
    'patients': 'patients',
    'appointments': 'appointments',
    'visits': 'visits',
    'billing_records': 'billing',
    'expenses': 'expenses',
    'treatment_procedures': 'treatment_procedures',
    'followups': 'patient_followups',
    'treatment_plans': 'treatment_plans',
    'holidays': 'holidays',
  };
  static final Map<String, String> remoteToLocalTable = {
    for (final e in localToRemoteTable.entries) e.value: e.key,
  };

  static const String _createTombstones = '''
    CREATE TABLE IF NOT EXISTS sync_tombstones (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      table_name TEXT NOT NULL,
      row_id INTEGER NOT NULL,
      deleted_at TEXT NOT NULL,
      is_synced INTEGER DEFAULT 0,
      UNIQUE(table_name, row_id)
    )
  ''';

  Future<void> _onUpgrade(Database db, int oldVersion, int newVersion) async {
    if (oldVersion < 2) {
      await db.execute(_createTombstones);
    }
    if (oldVersion < 3) {
      await db.execute(_createFollowups);
      await db.execute(_idxFollowupsPatient);
    }
    if (oldVersion < 4) {
      await db.execute(_createTreatmentPlans);
      await db.execute(_idxPlansPatient);
      await db.execute(_createHolidays);
      await db.execute(_idxHolidaysDate);
    }
  }

  static const String _createTreatmentPlans = '''
    CREATE TABLE IF NOT EXISTS treatment_plans (
      id INTEGER PRIMARY KEY,
      patient_id INTEGER NOT NULL,
      plan_name TEXT NOT NULL,
      goals TEXT,
      estimated_cost REAL DEFAULT 0,
      status TEXT DEFAULT 'draft',
      start_date TEXT,
      end_date TEXT,
      notes TEXT,
      updated_at TEXT,
      is_synced INTEGER DEFAULT 0
    )
  ''';

  static const String _idxPlansPatient =
      'CREATE INDEX IF NOT EXISTS idx_plans_patient ON treatment_plans(patient_id)';

  static const String _createHolidays = '''
    CREATE TABLE IF NOT EXISTS holidays (
      id INTEGER PRIMARY KEY,
      holiday_date TEXT NOT NULL,
      name TEXT,
      notes TEXT,
      updated_at TEXT,
      is_synced INTEGER DEFAULT 0
    )
  ''';

  static const String _idxHolidaysDate =
      'CREATE INDEX IF NOT EXISTS idx_holidays_date ON holidays(holiday_date)';

  static const String _createFollowups = '''
    CREATE TABLE IF NOT EXISTS followups (
      id INTEGER PRIMARY KEY,
      patient_id INTEGER NOT NULL,
      followup_date TEXT,
      treatment_procedure TEXT,
      procedure_id INTEGER,
      tooth_no TEXT,
      diagnosis TEXT,
      price REAL DEFAULT 0,
      discount REAL DEFAULT 0,
      lab_expense REAL DEFAULT 0,
      payment REAL DEFAULT 0,
      remaining_amount REAL DEFAULT 0,
      clinic_profit REAL DEFAULT 0,
      notes TEXT,
      updated_at TEXT,
      is_synced INTEGER DEFAULT 0
    )
  ''';

  static const String _idxFollowupsPatient =
      'CREATE INDEX IF NOT EXISTS idx_followups_patient ON followups(patient_id)';

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

    await db.execute(_createTombstones);
    await db.execute(_createFollowups);
    await db.execute(_idxFollowupsPatient);
    await db.execute(_createTreatmentPlans);
    await db.execute(_idxPlansPatient);
    await db.execute(_createHolidays);
    await db.execute(_idxHolidaysDate);
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
    await recordTombstone('patients', id);
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
    await recordTombstone('appointments', id);
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
    await recordTombstone('visits', id);
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
    await recordTombstone('expenses', id);
  }

  // ── Follow-ups ────────────────────────────────────────────────────────────

  Future<List<Followup>> getPatientFollowups(int patientId) async {
    final db = await database;
    final rows = await db.query('followups',
        where: 'patient_id = ?',
        whereArgs: [patientId],
        orderBy: 'followup_date ASC, id ASC');
    return rows.map(Followup.fromDb).toList();
  }

  Future<Followup?> getFollowup(int id) async {
    final db = await database;
    final rows = await db
        .query('followups', where: 'id = ?', whereArgs: [id], limit: 1);
    return rows.isEmpty ? null : Followup.fromDb(rows.first);
  }

  /// Insert or update a follow-up, then rewrite the running balance for the
  /// whole patient ledger. Returns the row id.
  Future<int> upsertFollowup(Followup f) async {
    final db = await database;
    final data = f.toDb();
    int rowId;
    if (f.id != null) {
      final exists = await db.query('followups',
          where: 'id = ?', whereArgs: [f.id], limit: 1);
      if (exists.isNotEmpty) {
        await db.update('followups', data, where: 'id = ?', whereArgs: [f.id]);
        rowId = f.id!;
      } else {
        rowId = await db.insert('followups', data,
            conflictAlgorithm: ConflictAlgorithm.replace);
      }
    } else {
      rowId = await db.insert('followups', data,
          conflictAlgorithm: ConflictAlgorithm.replace);
    }
    await _recomputeFollowupBalances(f.patientId);
    return rowId;
  }

  Future<void> deleteFollowup({required int id, required int patientId}) async {
    final db = await database;
    await db.delete('followups', where: 'id = ?', whereArgs: [id]);
    await recordTombstone('followups', id);
    await _recomputeFollowupBalances(patientId);
  }

  /// Port of the server's `_recompute_followup_balances`: rewrite every row's
  /// `remaining_amount` as the cumulative `Σ (price − discount − payment)`
  /// walked in `(followup_date ASC, id ASC)` order. May go negative (patient
  /// credit) — no clamping, matching the server.
  Future<void> _recomputeFollowupBalances(int patientId) async {
    final db = await database;
    final rows = await db.query('followups',
        columns: ['id', 'price', 'discount', 'payment', 'remaining_amount'],
        where: 'patient_id = ?',
        whereArgs: [patientId],
        orderBy: 'followup_date ASC, id ASC');
    double running = 0.0;
    final batch = db.batch();
    var dirty = false;
    for (final r in rows) {
      final price = (r['price'] as num?)?.toDouble() ?? 0.0;
      final discount = (r['discount'] as num?)?.toDouble() ?? 0.0;
      final payment = (r['payment'] as num?)?.toDouble() ?? 0.0;
      running += price - discount - payment;
      final newAmount = (running * 100).round() / 100;
      final stored = (r['remaining_amount'] as num?)?.toDouble() ?? 0.0;
      if ((newAmount - stored).abs() > 0.005) {
        batch.update('followups', {'remaining_amount': newAmount},
            where: 'id = ?', whereArgs: [r['id']]);
        dirty = true;
      }
    }
    if (dirty) await batch.commit(noResult: true);
  }

  /// Test seam: the recompute is private but tests need to verify it directly
  /// for edge cases (out-of-order insertion, edit changing the date, etc.).
  Future<void> debugRecomputeFollowups(int patientId) =>
      _recomputeFollowupBalances(patientId);

  // ── Treatment Plans ───────────────────────────────────────────────────────

  Future<List<TreatmentPlan>> getPatientTreatmentPlans(int patientId) async {
    final db = await database;
    final rows = await db.query('treatment_plans',
        where: 'patient_id = ?',
        whereArgs: [patientId],
        orderBy: 'COALESCE(start_date, "") DESC, id DESC');
    return rows.map(TreatmentPlan.fromDb).toList();
  }

  Future<int> upsertTreatmentPlan(TreatmentPlan p) async {
    final db = await database;
    final data = p.toDb();
    if (p.id != null) {
      final exists = await db.query('treatment_plans',
          where: 'id = ?', whereArgs: [p.id], limit: 1);
      if (exists.isNotEmpty) {
        await db.update('treatment_plans', data,
            where: 'id = ?', whereArgs: [p.id]);
        return p.id!;
      }
    }
    return db.insert('treatment_plans', data,
        conflictAlgorithm: ConflictAlgorithm.replace);
  }

  Future<void> deleteTreatmentPlan(int id) async {
    final db = await database;
    await db.delete('treatment_plans', where: 'id = ?', whereArgs: [id]);
    await recordTombstone('treatment_plans', id);
  }

  // ── Holidays ──────────────────────────────────────────────────────────────

  Future<List<Holiday>> getHolidays() async {
    final db = await database;
    final rows = await db.query('holidays', orderBy: 'holiday_date ASC');
    return rows.map(Holiday.fromDb).toList();
  }

  /// Returns the calendar dates that fall on a clinic holiday. Used by the
  /// appointments calendar to grey them out.
  Future<Set<DateTime>> getHolidayDates() async {
    final db = await database;
    final rows = await db.query('holidays', columns: ['holiday_date']);
    final out = <DateTime>{};
    for (final r in rows) {
      final s = r['holiday_date']?.toString();
      if (s == null || s.isEmpty) continue;
      final dt = DateTime.tryParse(s);
      if (dt != null) out.add(DateTime(dt.year, dt.month, dt.day));
    }
    return out;
  }

  Future<int> upsertHoliday(Holiday h) async {
    final db = await database;
    final data = h.toDb();
    if (h.id != null) {
      final exists = await db.query('holidays',
          where: 'id = ?', whereArgs: [h.id], limit: 1);
      if (exists.isNotEmpty) {
        await db.update('holidays', data, where: 'id = ?', whereArgs: [h.id]);
        return h.id!;
      }
    }
    return db.insert('holidays', data,
        conflictAlgorithm: ConflictAlgorithm.replace);
  }

  Future<void> deleteHoliday(int id) async {
    final db = await database;
    await db.delete('holidays', where: 'id = ?', whereArgs: [id]);
    await recordTombstone('holidays', id);
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

  // ── Tombstones (deletion propagation) ─────────────────────────────────────

  /// Record that a row was deleted locally so the deletion can be synced.
  /// [localTable] is a local table name; it's stored under the server-side name.
  Future<void> recordTombstone(String localTable, int rowId) async {
    final remote = localToRemoteTable[localTable] ?? localTable;
    final db = await database;
    await db.insert(
      'sync_tombstones',
      {
        'table_name': remote,
        'row_id': rowId,
        'deleted_at': DateTime.now().toUtc().toIso8601String(),
        'is_synced': 0,
      },
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  /// Tombstones not yet pushed, shaped for `/api/sync/import` (`{table_name,row_id,deleted_at}`).
  Future<List<Map<String, dynamic>>> getUnsyncedTombstones() async {
    final db = await database;
    final rows = await db.query('sync_tombstones',
        columns: ['table_name', 'row_id', 'deleted_at'], where: 'is_synced = 0');
    return rows.map((r) => Map<String, dynamic>.from(r)).toList();
  }

  Future<void> markAllTombstonesSynced() async {
    final db = await database;
    await db.update('sync_tombstones', {'is_synced': 1}, where: 'is_synced = 0');
  }

  /// Apply a tombstone received from the server: delete the matching local row
  /// (and forget any local tombstone for it). [remoteTable] is a server-side name.
  Future<void> applyTombstone(String remoteTable, int rowId) async {
    final localTable = remoteToLocalTable[remoteTable];
    final db = await database;
    if (localTable != null) {
      await db.delete(localTable, where: 'id = ?', whereArgs: [rowId]);
    }
    await db.delete('sync_tombstones',
        where: 'table_name = ? AND row_id = ?', whereArgs: [remoteTable, rowId]);
  }
}
