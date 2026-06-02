import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/tooth_condition.dart';
import '../models/tooth_chart_entry.dart';
import '../services/tooth_chart_service.dart';
import '../state/app_state.dart';

const _upperFdi = [
  '18', '17', '16', '15', '14', '13', '12', '11',
  '21', '22', '23', '24', '25', '26', '27', '28',
];
const _lowerFdi = [
  '48', '47', '46', '45', '44', '43', '42', '41',
  '31', '32', '33', '34', '35', '36', '37', '38',
];

String _fdiClass(String fdi) {
  final n = int.parse(fdi[1]);
  if (n <= 2) return 'incisor';
  if (n == 3) return 'canine';
  if (n <= 5) return 'premolar';
  return 'molar';
}

Color _colorFromHex(String? hex) {
  if (hex == null || !hex.startsWith('#')) return const Color(0x00000000);
  final cleaned = hex.substring(1);
  if (cleaned.length != 6) return const Color(0x00000000);
  return Color(int.parse(cleaned, radix: 16) | 0xFF000000);
}

/// Abstract interface so the widget test can inject a fake service
/// without spinning up a real ClinicApi / DatabaseService.
abstract class ToothChartReader {
  Future<ToothChart> getChart(int patientId);
  Future<void> setTooth(int patientId, String toothNo, int? conditionId,
      {String? note});
  Future<void> clearTooth(int patientId, String toothNo);
  Future<List<ToothCondition>> getConditions({bool all = false});
}

/// Adapts the concrete ToothChartService to the abstract interface.
class _RealChartReader implements ToothChartReader {
  final ToothChartService _svc;
  _RealChartReader(this._svc);

  @override
  Future<ToothChart> getChart(int id) => _svc.getChart(id);

  @override
  Future<void> setTooth(int pid, String t, int? cid, {String? note}) =>
      _svc.setTooth(pid, t, cid, note: note);

  @override
  Future<void> clearTooth(int pid, String t) => _svc.clearTooth(pid, t);

  @override
  Future<List<ToothCondition>> getConditions({bool all = false}) =>
      _svc.getConditions(all: all);
}

/// Full FDI arch for a single patient.  Tap a tooth → condition sheet.
class OdontogramView extends StatefulWidget {
  final int patientId;
  final ToothChartReader? reader; // nullable: uses real service from AppState
  final void Function(String toothNo)? onLogTreatment;
  final void Function(String toothNo)? onAddToPlan;

  const OdontogramView({
    super.key,
    required this.patientId,
    this.reader,
    this.onLogTreatment,
    this.onAddToPlan,
  });

  @override
  State<OdontogramView> createState() => _OdontogramViewState();
}

class _OdontogramViewState extends State<OdontogramView> {
  ToothChart? _chart;
  bool _loading = true;
  String? _error;

  late ToothChartReader _reader;

  @override
  void initState() {
    super.initState();
    _reader = widget.reader ??
        _RealChartReader(
          ToothChartService(
            context.read<AppState>().db,
            context.read<AppState>().api,
          ),
        );
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final chart = await _reader.getChart(widget.patientId);
      if (mounted) setState(() => _chart = chart);
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _tapTooth(String fdi) {
    final chart = _chart;
    if (chart == null) return;
    final entry = chart.teeth[fdi];
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _ToothSheet(
        fdi: fdi,
        entry: entry,
        conditions: chart.conditions,
        reader: _reader,
        patientId: widget.patientId,
        onSaved: _load,
        onLogTreatment: widget.onLogTreatment,
        onAddToPlan: widget.onAddToPlan,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final isArabic = context.select<AppState, bool>((s) => s.isArabic);

    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.error_outline, color: scheme.error, size: 40),
              const SizedBox(height: 12),
              Text(
                isArabic
                    ? 'تعذّر تحميل خريطة الأسنان'
                    : 'Could not load tooth chart',
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 8),
              FilledButton.icon(
                onPressed: _load,
                icon: const Icon(Icons.refresh),
                label: Text(isArabic ? 'إعادة المحاولة' : 'Retry'),
              ),
            ],
          ),
        ),
      );
    }

    final chart = _chart!;

    return RefreshIndicator(
      onRefresh: _load,
      child: SingleChildScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Legend
            if (chart.conditions.isNotEmpty) ...[
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Text(
                  isArabic ? 'دليل الألوان' : 'Legend',
                  style: const TextStyle(
                      fontWeight: FontWeight.w700, fontSize: 13),
                ),
              ),
              Wrap(
                spacing: 8,
                runSpacing: 4,
                children: chart.conditions.map((c) {
                  return Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        width: 14,
                        height: 14,
                        decoration: BoxDecoration(
                          color: _colorFromHex(c.color),
                          borderRadius: BorderRadius.circular(3),
                          border: Border.all(color: scheme.outlineVariant),
                        ),
                      ),
                      const SizedBox(width: 4),
                      Text(
                        isArabic && c.nameAr != null ? c.nameAr! : c.name,
                        style: const TextStyle(fontSize: 12),
                      ),
                    ],
                  );
                }).toList(),
              ),
              const SizedBox(height: 12),
            ],

            // Badge legend
            Row(
              children: [
                _badgeDot(const Color(0xFF7C3AED)),
                const SizedBox(width: 4),
                Text(isArabic ? 'خطة علاجية' : 'In plan',
                    style: const TextStyle(fontSize: 11)),
                const SizedBox(width: 12),
                _badgeDot(const Color(0xFFF59E0B)),
                const SizedBox(width: 4),
                Text(isArabic ? 'رصيد غير مدفوع' : 'Unpaid balance',
                    style: const TextStyle(fontSize: 11)),
              ],
            ),
            const SizedBox(height: 16),

            // Upper arch label
            Text(
              isArabic ? 'الفك العلوي' : 'Upper',
              style: TextStyle(
                  fontSize: 11, color: scheme.onSurfaceVariant),
            ),
            const SizedBox(height: 6),
            _ArchRow(
              teeth: _upperFdi,
              chart: chart.teeth,
              onTap: _tapTooth,
            ),

            const SizedBox(height: 8),

            // Lower arch label
            Text(
              isArabic ? 'الفك السفلي' : 'Lower',
              style: TextStyle(
                  fontSize: 11, color: scheme.onSurfaceVariant),
            ),
            const SizedBox(height: 6),
            _ArchRow(
              teeth: _lowerFdi,
              chart: chart.teeth,
              onTap: _tapTooth,
            ),

            const SizedBox(height: 24),
          ],
        ),
      ),
    );
  }

  Widget _badgeDot(Color c) => Container(
        width: 10,
        height: 10,
        decoration: BoxDecoration(color: c, shape: BoxShape.circle),
      );
}

/// A single row of 16 teeth (upper or lower arch).
class _ArchRow extends StatelessWidget {
  final List<String> teeth;
  final Map<String, ToothChartEntry> chart;
  final void Function(String) onTap;

  const _ArchRow({
    required this.teeth,
    required this.chart,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: teeth.map((fdi) {
        final entry = chart[fdi];
        return GestureDetector(
          onTap: () => onTap(fdi),
          child: _ToothCell(fdi: fdi, entry: entry),
        );
      }).toList(),
    );
  }
}

/// One tooth cell rendered with CustomPaint.
class _ToothCell extends StatelessWidget {
  final String fdi;
  final ToothChartEntry? entry;

  const _ToothCell({required this.fdi, this.entry});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final fillColor = entry?.color != null
        ? _colorFromHex(entry!.color)
        : Colors.transparent;
    final hasFill = entry?.conditionId != null;
    final hasPlan = entry?.hasPlan ?? false;
    final hasUnpaid = (entry?.unpaidBalance ?? 0) > 0;

    return Padding(
      padding: const EdgeInsets.all(1.5),
      child: SizedBox(
        width: 18,
        height: 26,
        child: Stack(
          alignment: Alignment.center,
          children: [
            CustomPaint(
              size: const Size(18, 24),
              painter: _ToothPainter(
                toothClass: _fdiClass(fdi),
                fillColor: hasFill ? fillColor : Colors.transparent,
                outlineColor: hasFill
                    ? fillColor.withAlpha(200)
                    : scheme.outlineVariant,
              ),
            ),
            // Plan badge (purple dot, top-right)
            if (hasPlan)
              Positioned(
                top: 0,
                right: 0,
                child: Container(
                  width: 6,
                  height: 6,
                  decoration: const BoxDecoration(
                    color: Color(0xFF7C3AED),
                    shape: BoxShape.circle,
                  ),
                ),
              ),
            // Unpaid badge (amber dot, bottom-right)
            if (hasUnpaid)
              Positioned(
                bottom: 0,
                right: 0,
                child: Container(
                  width: 6,
                  height: 6,
                  decoration: const BoxDecoration(
                    color: Color(0xFFF59E0B),
                    shape: BoxShape.circle,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _ToothPainter extends CustomPainter {
  final String toothClass;
  final Color fillColor;
  final Color outlineColor;

  const _ToothPainter({
    required this.toothClass,
    required this.fillColor,
    required this.outlineColor,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final fill = Paint()
      ..color = fillColor
      ..style = PaintingStyle.fill;
    final stroke = Paint()
      ..color = outlineColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.2;

    final path = _buildPath(size);
    canvas.drawPath(path, fill);
    canvas.drawPath(path, stroke);
  }

  Path _buildPath(Size s) {
    final w = s.width;
    final h = s.height;
    final path = Path();

    switch (toothClass) {
      case 'molar':
        // Rounded rectangle with flat cusp hint at top
        path.addRRect(RRect.fromRectAndRadius(
          Rect.fromLTWH(1, 2, w - 2, h - 3),
          const Radius.circular(3),
        ));
      case 'premolar':
        path.addRRect(RRect.fromRectAndRadius(
          Rect.fromLTWH(1.5, 3, w - 3, h - 4),
          const Radius.circular(3),
        ));
      case 'canine':
        // Pointed tip
        path
          ..moveTo(w / 2, 1)
          ..lineTo(w - 1.5, 5)
          ..lineTo(w - 1.5, h - 2)
          ..arcToPoint(Offset(1.5, h - 2),
              radius: const Radius.circular(2))
          ..lineTo(1.5, 5)
          ..close();
      default: // incisor — blade shape
        path.addRRect(RRect.fromRectAndRadius(
          Rect.fromLTWH(2, 3, w - 4, h - 4),
          const Radius.circular(2),
        ));
    }
    return path;
  }

  @override
  bool shouldRepaint(_ToothPainter old) =>
      old.toothClass != toothClass ||
      old.fillColor != fillColor ||
      old.outlineColor != outlineColor;
}

// ─── Tap sheet ──────────────────────────────────────────────────────────────

class _ToothSheet extends StatefulWidget {
  final String fdi;
  final ToothChartEntry? entry;
  final List<ToothCondition> conditions;
  final ToothChartReader reader;
  final int patientId;
  final VoidCallback onSaved;
  final void Function(String toothNo)? onLogTreatment;
  final void Function(String toothNo)? onAddToPlan;

  const _ToothSheet({
    required this.fdi,
    required this.entry,
    required this.conditions,
    required this.reader,
    required this.patientId,
    required this.onSaved,
    this.onLogTreatment,
    this.onAddToPlan,
  });

  @override
  State<_ToothSheet> createState() => _ToothSheetState();
}

class _ToothSheetState extends State<_ToothSheet> {
  int? _selectedConditionId;
  late final TextEditingController _note;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _selectedConditionId = widget.entry?.conditionId;
    _note = TextEditingController(text: widget.entry?.note ?? '');
  }

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      if (_selectedConditionId == null) {
        await widget.reader.clearTooth(widget.patientId, widget.fdi);
      } else {
        await widget.reader.setTooth(
          widget.patientId,
          widget.fdi,
          _selectedConditionId,
          note: _note.text.trim().isEmpty ? null : _note.text.trim(),
        );
      }
      if (mounted) Navigator.pop(context);
      widget.onSaved();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$e')));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final isArabic = context.select<AppState, bool>((s) => s.isArabic);
    final scheme = Theme.of(context).colorScheme;

    final conditionItems = [
      DropdownMenuItem<int?>(
        value: null,
        child: Text(isArabic ? 'سليم / مسح' : 'Healthy / clear'),
      ),
      ...widget.conditions.map(
        (c) => DropdownMenuItem<int?>(
          value: c.id,
          child: Row(
            children: [
              Container(
                width: 12,
                height: 12,
                margin: const EdgeInsets.only(left: 4),
                decoration: BoxDecoration(
                  color: _colorFromHex(c.color),
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              const SizedBox(width: 6),
              Text(isArabic && c.nameAr != null ? c.nameAr! : c.name),
            ],
          ),
        ),
      ),
    ];

    return Padding(
      padding:
          EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: Container(
        decoration: BoxDecoration(
          color: Theme.of(context).scaffoldBackgroundColor,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
        ),
        child: SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Center(
                  child: Container(
                    width: 40,
                    height: 4,
                    margin: const EdgeInsets.only(bottom: 12),
                    decoration: BoxDecoration(
                      color: scheme.outlineVariant,
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ),
                ),
                Text(
                  '${isArabic ? 'السن' : 'Tooth'} #${widget.fdi}',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<int?>(
                  initialValue: _selectedConditionId,
                  decoration: InputDecoration(
                    labelText: isArabic ? 'الحالة' : 'Condition',
                    border: const OutlineInputBorder(),
                  ),
                  items: conditionItems,
                  onChanged: (v) => setState(() => _selectedConditionId = v),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _note,
                  decoration: InputDecoration(
                    labelText: isArabic ? 'ملاحظة' : 'Note',
                    border: const OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 12),
                FilledButton.icon(
                  onPressed: _saving ? null : _save,
                  icon: const Icon(Icons.save_outlined),
                  label: Text(isArabic ? 'حفظ' : 'Save'),
                ),
                const SizedBox(height: 8),
                if (widget.onLogTreatment != null)
                  OutlinedButton.icon(
                    onPressed: () {
                      Navigator.pop(context);
                      widget.onLogTreatment!(widget.fdi);
                    },
                    icon: const Icon(Icons.add_circle_outline),
                    label: Text(isArabic ? '+ تسجيل علاج' : '+ Log treatment'),
                  ),
                if (widget.onAddToPlan != null) ...[
                  const SizedBox(height: 8),
                  OutlinedButton.icon(
                    onPressed: () {
                      Navigator.pop(context);
                      widget.onAddToPlan!(widget.fdi);
                    },
                    icon: const Icon(Icons.playlist_add_outlined),
                    label:
                        Text(isArabic ? '+ إضافة للخطة' : '+ Add to plan'),
                  ),
                ],
                const SizedBox(height: 8),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
