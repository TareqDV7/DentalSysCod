/// One tooth's state as returned by GET /api/patients/{id}/tooth-chart.
/// `hasPlan` / `unpaidBalance` are server-computed badges (never stored).
class ToothChartEntry {
  final String toothNo;
  final int? conditionId;
  final String? conditionName;
  final String? color;
  final String? note;
  final String source; // 'chart' | 'legacy'
  final bool hasPlan;
  final double unpaidBalance;

  const ToothChartEntry({
    required this.toothNo,
    this.conditionId,
    this.conditionName,
    this.color,
    this.note,
    this.source = 'chart',
    this.hasPlan = false,
    this.unpaidBalance = 0,
  });

  factory ToothChartEntry.fromJson(String toothNo, Map<String, dynamic> j) =>
      ToothChartEntry(
        toothNo: toothNo,
        conditionId: j['condition_id'] is int
            ? j['condition_id'] as int
            : int.tryParse('${j['condition_id']}'),
        conditionName: j['condition_name']?.toString(),
        color: j['color']?.toString(),
        note: j['note']?.toString(),
        source: (j['source'] ?? 'chart').toString(),
        hasPlan: j['has_plan'] == true || j['has_plan'] == 1,
        unpaidBalance: _num(j['unpaid_balance']),
      );

  static double _num(dynamic v) {
    if (v == null) return 0;
    if (v is num) return v.toDouble();
    return double.tryParse(v.toString()) ?? 0;
  }
}
