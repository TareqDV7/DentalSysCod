import '../models/billing_account.dart';
import '../models/billing_record.dart';
import '../models/expense.dart';
import 'database_service.dart';
import 'clinic_api.dart';

class BillingService {
  final DatabaseService _db;
  final ClinicApi _api;

  BillingService(this._db, this._api);

  // ── Billing records ───────────────────────────────────────────────────────

  Future<List<BillingRecord>> getBillingRecords({int? patientId}) =>
      _db.getBillingRecords(patientId: patientId);

  Future<BillingRecord> addBillingRecord(BillingRecord b) async {
    final now = DateTime.now().toIso8601String();
    final local = BillingRecord(
      patientId: b.patientId,
      patientName: b.patientName,
      subtotal: b.subtotal,
      discount: b.discount,
      paidAmount: b.paidAmount,
      creditUsed: b.creditUsed,
      paymentMethod: b.paymentMethod,
      paymentDate: b.paymentDate ?? now.substring(0, 10),
      subtotalExpr: b.subtotalExpr,
      discountExpr: b.discountExpr,
      paidAmountExpr: b.paidAmountExpr,
      updatedAt: now,
      isSynced: false,
    );
    final localId = await _db.upsertBillingRecord(local);

    try {
      final res = await _api.post('/api/billing', body: local.toJson());
      final remote = BillingRecord.fromJson(res);
      await _db.upsertBillingRecord(
          BillingRecord.fromDb({...remote.toDb(), 'is_synced': 1}));
      return remote;
    } catch (_) {
      return BillingRecord.fromDb({...local.toDb(), 'id': localId});
    }
  }

  /// Delete a billing record (reverses applied credit + tombstones for sync).
  /// Best-effort direct server delete too, so a connected node drops it
  /// immediately; offline, the tombstone propagates on the next sync.
  Future<void> deleteBillingRecord(int id) async {
    await _db.deleteBillingRecord(id);
    try {
      await _api.delete('/api/billing/$id');
    } catch (_) {/* offline — tombstone will carry the delete */}
  }

  Future<List<Map<String, dynamic>>> getReceivables() =>
      _db.getReceivables();

  /// Per-patient billing rolled up from the follow-up sheets (charged / paid /
  /// balance), so the Billing tab mirrors each patient's sheet.
  Future<List<BillingAccount>> getBillingAccounts() async =>
      (await _db.getBillingAccounts())
          .map(BillingAccount.fromRow)
          .toList();

  // ── Expenses ──────────────────────────────────────────────────────────────

  Future<List<Expense>> getExpenses({String? period, String? status}) =>
      _db.getExpenses(period: period, status: status);

  Future<Expense> addExpense(Expense e) async {
    final now = DateTime.now().toIso8601String();
    final local = Expense(
      category: e.category,
      amount: e.amount,
      expenseDate: e.expenseDate ?? now.substring(0, 10),
      status: e.status,
      vendor: e.vendor,
      notes: e.notes,
      updatedAt: now,
      isSynced: false,
    );
    final localId = await _db.upsertExpense(local);

    try {
      final res = await _api.post('/api/expenses', body: local.toJson());
      final remote = Expense.fromJson(res);
      await _db.upsertExpense(remote);
      return remote;
    } catch (_) {
      return Expense.fromDb({...local.toDb(), 'id': localId});
    }
  }

  Future<void> deleteExpense(int id) async {
    await _db.deleteExpense(id);
    try {
      await _api.post('/api/expenses/$id/delete', body: {});
    } catch (_) {}
  }

  Future<Expense> updateExpenseStatus(int id, String status) async {
    final all = await _db.getExpenses();
    final existing = all.where((e) => e.id == id).firstOrNull;
    if (existing == null) throw Exception('Expense $id not found');
    final updated = Expense(
      id: id,
      category: existing.category,
      amount: existing.amount,
      expenseDate: existing.expenseDate,
      status: status,
      vendor: existing.vendor,
      notes: existing.notes,
      updatedAt: DateTime.now().toIso8601String(),
      isSynced: false,
    );
    await _db.upsertExpense(updated);
    try {
      await _api.post('/api/expenses/$id', body: {'status': status});
    } catch (_) {}
    return updated;
  }
}
