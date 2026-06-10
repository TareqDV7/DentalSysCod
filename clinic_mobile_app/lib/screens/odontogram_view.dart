import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/tooth_condition.dart';
import '../models/tooth_chart_entry.dart';
import '../services/tooth_chart_service.dart';
import '../state/app_state.dart';

const _upperFdi = [
  '18',
  '17',
  '16',
  '15',
  '14',
  '13',
  '12',
  '11',
  '21',
  '22',
  '23',
  '24',
  '25',
  '26',
  '27',
  '28',
];
const _lowerFdi = [
  '48',
  '47',
  '46',
  '45',
  '44',
  '43',
  '42',
  '41',
  '31',
  '32',
  '33',
  '34',
  '35',
  '36',
  '37',
  '38',
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
  Future<void> setToothConditions(
    int patientId,
    String toothNo,
    List<({int conditionId, String? note})> conditions,
  );
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
  Future<void> setToothConditions(
    int pid,
    String t,
    List<({int conditionId, String? note})> conditions,
  ) => _svc.setToothConditions(pid, t, conditions);

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
    _reader =
        widget.reader ??
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
                    fontWeight: FontWeight.w700,
                    fontSize: 13,
                  ),
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
                Text(
                  isArabic ? 'خطة علاجية' : 'In plan',
                  style: const TextStyle(fontSize: 11),
                ),
                const SizedBox(width: 12),
                _badgeDot(const Color(0xFFF59E0B)),
                const SizedBox(width: 4),
                Text(
                  isArabic ? 'رصيد غير مدفوع' : 'Unpaid balance',
                  style: const TextStyle(fontSize: 11),
                ),
              ],
            ),
            const SizedBox(height: 16),

            // Upper arch label
            Text(
              isArabic ? 'الفك العلوي' : 'Upper',
              style: TextStyle(fontSize: 11, color: scheme.onSurfaceVariant),
            ),
            const SizedBox(height: 6),
            _ArchRow(teeth: _upperFdi, chart: chart.teeth, onTap: _tapTooth),

            const SizedBox(height: 8),

            // Lower arch label
            Text(
              isArabic ? 'الفك السفلي' : 'Lower',
              style: TextStyle(fontSize: 11, color: scheme.onSurfaceVariant),
            ),
            const SizedBox(height: 6),
            _ArchRow(teeth: _lowerFdi, chart: chart.teeth, onTap: _tapTooth),

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
    return Directionality(
      textDirection: TextDirection.ltr,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: teeth.map((fdi) {
          final entry = chart[fdi];
          return GestureDetector(
            onTap: () => onTap(fdi),
            child: _ToothCell(fdi: fdi, entry: entry),
          );
        }).toList(),
      ),
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
    final hasPlan = entry?.hasPlan ?? false;
    final hasUnpaid = (entry?.unpaidBalance ?? 0) > 0;
    final bandColors = [
      for (final c in (entry?.conditions ?? const <ToothConditionTag>[]))
        _colorFromHex(c.color),
    ];

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
                bandColors: bandColors,
                outlineColor: (entry?.hasConditions ?? false)
                    ? const Color(0xFF334155)
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
  final List<Color> bandColors;
  final Color outlineColor;

  const _ToothPainter({
    required this.toothClass,
    required this.bandColors,
    required this.outlineColor,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final path = _buildPath(size);
    if (bandColors.isNotEmpty) {
      canvas.save();
      canvas.clipPath(path);
      final bandH = size.height / bandColors.length;
      for (var i = 0; i < bandColors.length; i++) {
        final r = Rect.fromLTWH(0, i * bandH, size.width, bandH);
        canvas.drawRect(r, Paint()..color = bandColors[i]);
      }
      canvas.restore();
    }
    canvas.drawPath(
      path,
      Paint()
        ..color = outlineColor
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.2,
    );
  }

  Path _buildPath(Size s) {
    final w = s.width;
    final h = s.height;
    final path = Path();
    switch (toothClass) {
      case 'molar':
        path.addRRect(
          RRect.fromRectAndRadius(
            Rect.fromLTWH(1, 2, w - 2, h - 3),
            const Radius.circular(4),
          ),
        );
      case 'premolar':
        path.addRRect(
          RRect.fromRectAndRadius(
            Rect.fromLTWH(2, 3, w - 4, h - 4),
            const Radius.circular(4),
          ),
        );
      case 'canine':
        path
          ..moveTo(w / 2, 1)
          ..lineTo(w - 2, 6)
          ..lineTo(w - 2.5, h - 3)
          ..arcToPoint(Offset(2.5, h - 3), radius: const Radius.circular(3))
          ..lineTo(2, 6)
          ..close();
      default: // incisor — flat blade
        path.addRRect(
          RRect.fromRectAndRadius(
            Rect.fromLTWH(2.5, 3, w - 5, h - 4),
            const Radius.circular(2),
          ),
        );
    }
    return path;
  }

  @override
  bool shouldRepaint(_ToothPainter old) =>
      old.toothClass != toothClass ||
      old.outlineColor != outlineColor ||
      !_sameColors(old.bandColors, bandColors);

  static bool _sameColors(List<Color> a, List<Color> b) {
    if (a.length != b.length) return false;
    for (var i = 0; i < a.length; i++) {
      if (a[i] != b[i]) return false;
    }
    return true;
  }
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
  // condition_id -> note controller
  final Map<int, TextEditingController> _notes = {};
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    for (final c in (widget.entry?.conditions ?? const <ToothConditionTag>[])) {
      _notes[c.conditionId] = TextEditingController(text: c.note ?? '');
    }
  }

  @override
  void dispose() {
    for (final c in _notes.values) {
      c.dispose();
    }
    super.dispose();
  }

  void _toggle(int conditionId) {
    setState(() {
      if (_notes.containsKey(conditionId)) {
        _notes.remove(conditionId)!.dispose();
      } else {
        _notes[conditionId] = TextEditingController();
      }
    });
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      final list = <({int conditionId, String? note})>[
        for (final e in _notes.entries)
          (
            conditionId: e.key,
            note: e.value.text.trim().isEmpty ? null : e.value.text.trim(),
          ),
      ];
      await widget.reader.setToothConditions(
        widget.patientId,
        widget.fdi,
        list,
      );
      if (mounted) Navigator.pop(context);
      widget.onSaved();
    } on Exception catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('$e')));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  String _condName(int id, bool isArabic) {
    final matches = widget.conditions.where((x) => x.id == id);
    if (matches.isEmpty) return '#$id';
    final cc = matches.first;
    return isArabic && cc.nameAr != null ? cc.nameAr! : cc.name;
  }

  @override
  Widget build(BuildContext context) {
    final isArabic = context.select<AppState, bool>((s) => s.isArabic);
    final scheme = Theme.of(context).colorScheme;

    return Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom,
      ),
      child: Container(
        decoration: BoxDecoration(
          color: Theme.of(context).scaffoldBackgroundColor,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
        ),
        child: SafeArea(
          top: false,
          child: SingleChildScrollView(
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
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: widget.conditions
                      .where((c) => c.name != 'Healthy')
                      .map((c) {
                        final selected = _notes.containsKey(c.id);
                        return FilterChip(
                          label: Text(
                            isArabic && c.nameAr != null ? c.nameAr! : c.name,
                          ),
                          avatar: CircleAvatar(
                            backgroundColor: _colorFromHex(c.color),
                            radius: 7,
                          ),
                          selected: selected,
                          onSelected: (_) => _toggle(c.id!),
                        );
                      })
                      .toList(),
                ),
                const SizedBox(height: 12),
                for (final e in _notes.entries) ...[
                  TextField(
                    controller: e.value,
                    decoration: InputDecoration(
                      isDense: true,
                      labelText: _condName(e.key, isArabic),
                      border: const OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 8),
                ],
                const SizedBox(height: 4),
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
                    label: Text(isArabic ? '+ إضافة للخطة' : '+ Add to plan'),
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
