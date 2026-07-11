import 'database_service.dart';
import 'clinic_api.dart';

class WeeklyReport {
  final String weekStart;
  final String weekEnd;
  final int visits;  // Maps to distinct_teeth for backward compatibility
  final int distinctTeeth;
  final int followUps;
  final double revenue;
  final double expenses;
  final double labExpenses;
  final double profit;

  WeeklyReport({
    required this.weekStart,
    required this.weekEnd,
    required this.visits,
    this.distinctTeeth = 0,
    this.followUps = 0,
    required this.revenue,
    required this.expenses,
    required this.labExpenses,
    required this.profit,
  });

  factory WeeklyReport.fromJson(Map<String, dynamic> j) => WeeklyReport(
        weekStart: j['week_start'] ?? '',
        weekEnd: j['week_end'] ?? '',
        visits: (j['distinct_teeth'] ?? j['visits'] ?? 0) as int,
        distinctTeeth: (j['distinct_teeth'] ?? 0) as int,
        followUps: (j['follow_ups'] ?? 0) as int,
        revenue: _d(j['revenue'] ?? 0),
        expenses: _d(j['expenses'] ?? 0),
        labExpenses: _d(j['lab_expenses'] ?? 0),
        profit: _d(j['profit'] ?? 0),
      );
}

class MonthlyReport {
  final String month;
  final int visits;
  final double revenue;
  final double expenses;
  final double profit;

  MonthlyReport({
    required this.month,
    required this.visits,
    required this.revenue,
    required this.expenses,
    required this.profit,
  });

  factory MonthlyReport.fromJson(Map<String, dynamic> j) => MonthlyReport(
        month: j['month'] ?? '',
        visits: (j['visits'] ?? 0) as int,
        revenue: _d(j['revenue'] ?? 0),
        expenses: _d(j['expenses'] ?? 0),
        profit: _d(j['profit'] ?? 0),
      );
}

class ReportService {
  final DatabaseService _db;
  final ClinicApi _api;

  ReportService(this._db, this._api);

  /// Unified gross-profit formula -- see
  /// docs/superpowers/specs/2026-07-11-unified-gross-profit-design.md.
  /// Charge-based (net-of-discount price/subtotal, not cash-collected),
  /// across both the follow-up sheet and billing, minus lab expense and
  /// general clinic expenses. Pure and static so it can be tested without a
  /// database, and so the desktop and offline-fallback formulas can never
  /// silently drift apart again.
  static double computeProfit({
    required double followupNetCharge,
    required double billingNetCharge,
    required double labExpense,
    required double expenses,
  }) =>
      followupNetCharge + billingNetCharge - labExpense - expenses;

  Future<WeeklyReport?> getWeeklyReport(DateTime weekStart) async {
    try {
      final start = weekStart.toIso8601String().substring(0, 10);
      final res = await _api.get('/api/reports/weekly',
          query: {'week_start': start});
      return WeeklyReport.fromJson(res);
    } catch (_) {
      return _localWeeklyReport(weekStart);
    }
  }

  Future<MonthlyReport?> getMonthlyReport(int year, int month) async {
    try {
      final m = '${year.toString().padLeft(4, '0')}-${month.toString().padLeft(2, '0')}';
      final res = await _api
          .get('/api/reports/summary', query: {'month': m, 'period': 'month'});
      return MonthlyReport.fromJson(res);
    } catch (_) {
      return _localMonthlyReport(year, month);
    }
  }

  Future<List<MonthlyReport>> getLast6Months() async {
    final results = <MonthlyReport>[];
    final now = DateTime.now();
    for (int i = 5; i >= 0; i--) {
      final dt = DateTime(now.year, now.month - i, 1);
      final r = await getMonthlyReport(dt.year, dt.month);
      if (r != null) results.add(r);
    }
    return results;
  }

  Future<WeeklyReport> _localWeeklyReport(DateTime weekStart) async {
    final db = await _db.database;
    final start = weekStart.toIso8601String().substring(0, 10);
    final end = weekStart
        .add(const Duration(days: 6))
        .toIso8601String()
        .substring(0, 10);

    final followupRows = await db.rawQuery(
        'SELECT COUNT(*) as cnt, '
        'COALESCE(SUM(COALESCE(price,0) - COALESCE(discount,0)),0) as net_charge, '
        'COALESCE(SUM(lab_expense),0) as lab '
        'FROM followups WHERE followup_date >= ? AND followup_date <= ?',
        [start, end]);
    final billingRows = await db.rawQuery(
        'SELECT COALESCE(SUM(COALESCE(subtotal,0) - COALESCE(discount,0)),0) as net_charge '
        'FROM billing_records WHERE payment_date >= ? AND payment_date <= ?',
        [start, end]);
    // Lab-requiring follow-ups auto-mirror their lab_expense into `expenses`
    // (source_type='followup', synced down from the desktop's identical
    // mechanism) so it shows up as a real payable. That's already counted
    // via followupRows' `lab` sum above -- excluding source_type='followup'
    // here avoids subtracting the same cost twice.
    final expRows = await db.rawQuery(
        'SELECT COALESCE(SUM(amount),0) as total FROM expenses '
        "WHERE expense_date >= ? AND expense_date <= ? AND status IN ('paid','postponed') "
        "AND (source_type IS NULL OR source_type != 'followup')",
        [start, end]);

    final visits = (followupRows.first['cnt'] as int?) ?? 0;
    final followupNetCharge = _d(followupRows.first['net_charge']);
    final billingNetCharge = _d(billingRows.first['net_charge']);
    final labExp = _d(followupRows.first['lab']);
    final expenses = _d(expRows.first['total']);
    final profit = computeProfit(
      followupNetCharge: followupNetCharge,
      billingNetCharge: billingNetCharge,
      labExpense: labExp,
      expenses: expenses,
    );

    return WeeklyReport(
      weekStart: start,
      weekEnd: end,
      visits: visits,
      revenue: followupNetCharge + billingNetCharge,
      expenses: expenses,
      labExpenses: labExp,
      profit: profit,
    );
  }

  Future<MonthlyReport> _localMonthlyReport(int year, int month) async {
    final db = await _db.database;
    final prefix =
        '${year.toString().padLeft(4, '0')}-${month.toString().padLeft(2, '0')}';

    final followupRows = await db.rawQuery(
        'SELECT COUNT(*) as cnt, '
        'COALESCE(SUM(COALESCE(price,0) - COALESCE(discount,0)),0) as net_charge, '
        'COALESCE(SUM(lab_expense),0) as lab '
        'FROM followups WHERE followup_date LIKE ?',
        ['$prefix%']);
    final billingRows = await db.rawQuery(
        'SELECT COALESCE(SUM(COALESCE(subtotal,0) - COALESCE(discount,0)),0) as net_charge '
        'FROM billing_records WHERE payment_date LIKE ?',
        ['$prefix%']);
    // See _localWeeklyReport's identical comment: excludes the auto-mirrored
    // lab_expense rows already counted via followupRows' `lab` sum above.
    final expRows = await db.rawQuery(
        'SELECT COALESCE(SUM(amount),0) as total FROM expenses '
        "WHERE expense_date LIKE ? AND status IN ('paid','postponed') "
        "AND (source_type IS NULL OR source_type != 'followup')",
        ['$prefix%']);

    final visits = (followupRows.first['cnt'] as int?) ?? 0;
    final followupNetCharge = _d(followupRows.first['net_charge']);
    final billingNetCharge = _d(billingRows.first['net_charge']);
    final labExp = _d(followupRows.first['lab']);
    final expenses = _d(expRows.first['total']);
    final profit = computeProfit(
      followupNetCharge: followupNetCharge,
      billingNetCharge: billingNetCharge,
      labExpense: labExp,
      expenses: expenses,
    );

    return MonthlyReport(
      month: prefix,
      visits: visits,
      revenue: followupNetCharge + billingNetCharge,
      expenses: expenses,
      profit: profit,
    );
  }
}

double _d(dynamic v) {
  if (v is double) return v;
  if (v is int) return v.toDouble();
  return double.tryParse(v?.toString() ?? '0') ?? 0;
}
