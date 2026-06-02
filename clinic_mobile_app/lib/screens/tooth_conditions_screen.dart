import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/tooth_condition.dart';
import '../services/tooth_chart_service.dart';
import '../state/app_state.dart';

Color _colorFromHex(String? hex) {
  if (hex == null || !hex.startsWith('#')) return const Color(0x00000000);
  final cleaned = hex.substring(1);
  if (cleaned.length != 6) return const Color(0x00000000);
  return Color(int.parse(cleaned, radix: 16) | 0xFF000000);
}

/// CRUD list for the tooth-condition catalog. Mirrors catalog_screen.dart:
/// soft-deactivate rather than hard-delete, bilingual labels, ₪-free (no
/// pricing on conditions).
class ToothConditionsScreen extends StatefulWidget {
  const ToothConditionsScreen({super.key});

  @override
  State<ToothConditionsScreen> createState() => _ToothConditionsScreenState();
}

class _ToothConditionsScreenState extends State<ToothConditionsScreen> {
  List<ToothCondition> _all = [];
  bool _loading = true;
  bool _showInactive = false;

  late ToothChartService _svc;

  @override
  void initState() {
    super.initState();
    final app = context.read<AppState>();
    _svc = ToothChartService(app.db, app.api);
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final rows = await _svc.getConditions(all: true);
      if (mounted) setState(() => _all = rows);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$e')));
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _addOrEdit({ToothCondition? existing}) async {
    final isArabic = context.read<AppState>().isArabic;
    final result = await showModalBottomSheet<ToothCondition>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _ConditionSheet(existing: existing, isArabic: isArabic),
    );
    if (result == null) return;
    try {
      if (existing == null) {
        await _svc.addCondition(result);
      } else {
        await _svc.updateCondition(result.copyWith(id: existing.id));
      }
      if (mounted) await _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$e')));
      }
    }
  }

  Future<void> _toggleActive(ToothCondition c) async {
    try {
      await _svc.updateCondition(c.copyWith(active: !c.active));
      if (mounted) await _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$e')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final isArabic = context.select<AppState, bool>((s) => s.isArabic);
    final scheme = Theme.of(context).colorScheme;
    final shown =
        _all.where((c) => _showInactive ? true : c.active).toList();

    return Scaffold(
      appBar: AppBar(
        title: Text(isArabic ? 'حالات الأسنان' : 'Tooth conditions'),
        actions: [
          IconButton(
            tooltip: isArabic ? 'إظهار الكل' : 'Show inactive',
            icon: Icon(_showInactive
                ? Icons.visibility
                : Icons.visibility_off_outlined),
            onPressed: () =>
                setState(() => _showInactive = !_showInactive),
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : shown.isEmpty
              ? Center(
                  child: Padding(
                    padding: const EdgeInsets.all(32),
                    child: Text(
                      isArabic
                          ? 'لا توجد حالات بعد — أضف أول حالة'
                          : 'No conditions yet — add your first one',
                      textAlign: TextAlign.center,
                      style:
                          TextStyle(color: scheme.onSurfaceVariant),
                    ),
                  ),
                )
              : RefreshIndicator(
                  onRefresh: _load,
                  child: ListView.separated(
                    padding: const EdgeInsets.all(16),
                    itemCount: shown.length,
                    separatorBuilder: (_, _) =>
                        const SizedBox(height: 8),
                    itemBuilder: (_, i) => _ConditionTile(
                      condition: shown[i],
                      onEdit: () => _addOrEdit(existing: shown[i]),
                      onToggleActive: () => _toggleActive(shown[i]),
                      isArabic: isArabic,
                    ),
                  ),
                ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _addOrEdit(),
        backgroundColor: scheme.primary,
        foregroundColor: Colors.white,
        icon: const Icon(Icons.add),
        label: Text(
          isArabic ? 'إضافة حالة' : 'Add condition',
          style: const TextStyle(fontWeight: FontWeight.w700),
        ),
      ),
    );
  }
}

class _ConditionTile extends StatelessWidget {
  const _ConditionTile({
    required this.condition,
    required this.onEdit,
    required this.onToggleActive,
    required this.isArabic,
  });

  final ToothCondition condition;
  final VoidCallback onEdit;
  final VoidCallback onToggleActive;
  final bool isArabic;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final inactive = !condition.active;

    return InkWell(
      borderRadius: BorderRadius.circular(14),
      onTap: onEdit,
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: inactive
              ? scheme.surfaceContainerHighest
              : scheme.surface,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: scheme.outlineVariant),
        ),
        child: Row(
          children: [
            // Color swatch
            Container(
              width: 24,
              height: 24,
              decoration: BoxDecoration(
                color: _colorFromHex(condition.color),
                borderRadius: BorderRadius.circular(5),
                border: Border.all(color: scheme.outlineVariant),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    condition.name,
                    style: TextStyle(
                      fontWeight: FontWeight.w700,
                      color: inactive ? scheme.onSurfaceVariant : null,
                      decoration:
                          inactive ? TextDecoration.lineThrough : null,
                    ),
                  ),
                  if (condition.nameAr != null)
                    Text(
                      condition.nameAr!,
                      style: TextStyle(
                        fontSize: 12,
                        color: scheme.onSurfaceVariant,
                      ),
                    ),
                ],
              ),
            ),
            IconButton(
              tooltip: inactive
                  ? (isArabic ? 'إعادة التفعيل' : 'Reactivate')
                  : (isArabic ? 'إلغاء التفعيل' : 'Deactivate'),
              icon: Icon(
                  inactive ? Icons.restore : Icons.archive_outlined),
              onPressed: onToggleActive,
            ),
          ],
        ),
      ),
    );
  }
}

// ─── Add / Edit sheet ────────────────────────────────────────────────────────

class _ConditionSheet extends StatefulWidget {
  const _ConditionSheet({this.existing, required this.isArabic});
  final ToothCondition? existing;
  final bool isArabic;

  @override
  State<_ConditionSheet> createState() => _ConditionSheetState();
}

class _ConditionSheetState extends State<_ConditionSheet> {
  late final TextEditingController _name;
  late final TextEditingController _nameAr;
  late final TextEditingController _color;
  late final TextEditingController _sort;
  bool _active = true;

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    _name = TextEditingController(text: e?.name ?? '');
    _nameAr = TextEditingController(text: e?.nameAr ?? '');
    _color = TextEditingController(text: e?.color ?? '#9ca3af');
    _sort = TextEditingController(
        text: (e?.sortOrder ?? 0) == 0 ? '' : (e!.sortOrder).toString());
    _active = e?.active ?? true;
  }

  @override
  void dispose() {
    _name.dispose();
    _nameAr.dispose();
    _color.dispose();
    _sort.dispose();
    super.dispose();
  }

  void _save() {
    final name = _name.text.trim();
    if (name.isEmpty) return;
    final result = ToothCondition(
      id: widget.existing?.id,
      name: name,
      nameAr: _nameAr.text.trim().isEmpty ? null : _nameAr.text.trim(),
      color: _color.text.trim().isEmpty ? '#9ca3af' : _color.text.trim(),
      sortOrder: int.tryParse(_sort.text) ?? 0,
      active: _active,
    );
    Navigator.of(context).pop(result);
  }

  @override
  Widget build(BuildContext context) {
    final isArabic = widget.isArabic;
    final isEdit = widget.existing != null;
    final scheme = Theme.of(context).colorScheme;
    final previewColor = _colorFromHex(_color.text);

    return Padding(
      padding: EdgeInsets.only(
          bottom: MediaQuery.of(context).viewInsets.bottom),
      child: Container(
        decoration: BoxDecoration(
          color: Theme.of(context).scaffoldBackgroundColor,
          borderRadius:
              const BorderRadius.vertical(top: Radius.circular(24)),
        ),
        child: SafeArea(
          top: false,
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Column(
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
                  isEdit
                      ? (isArabic ? 'تعديل الحالة' : 'Edit condition')
                      : (isArabic ? 'إضافة حالة' : 'Add condition'),
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: _name,
                  textInputAction: TextInputAction.next,
                  decoration: InputDecoration(
                    labelText: isArabic ? 'الاسم (إنجليزي)' : 'Name (EN)',
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _nameAr,
                  textInputAction: TextInputAction.next,
                  textDirection: TextDirection.rtl,
                  decoration: InputDecoration(
                    labelText: isArabic ? 'الاسم (عربي)' : 'Name (AR)',
                  ),
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _color,
                        textInputAction: TextInputAction.next,
                        decoration: InputDecoration(
                          labelText: isArabic ? 'اللون (Hex)' : 'Color (hex)',
                          hintText: '#9ca3af',
                        ),
                        onChanged: (_) => setState(() {}),
                      ),
                    ),
                    const SizedBox(width: 12),
                    AnimatedContainer(
                      duration: const Duration(milliseconds: 200),
                      width: 36,
                      height: 36,
                      decoration: BoxDecoration(
                        color: previewColor == const Color(0x00000000)
                            ? scheme.surfaceContainerHighest
                            : previewColor,
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: scheme.outlineVariant),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _sort,
                  keyboardType: TextInputType.number,
                  decoration: InputDecoration(
                    labelText: isArabic ? 'ترتيب العرض' : 'Sort order',
                  ),
                ),
                const SizedBox(height: 12),
                SwitchListTile.adaptive(
                  contentPadding: EdgeInsets.zero,
                  value: _active,
                  onChanged: (v) => setState(() => _active = v),
                  title: Text(isArabic ? 'مفعّل' : 'Active'),
                  subtitle: Text(isArabic
                      ? 'يظهر في قائمة اختيار الحالة عند النقر على السن'
                      : 'Appears in the condition picker when tapping a tooth'),
                ),
                const SizedBox(height: 12),
                FilledButton.icon(
                  onPressed: _save,
                  icon: const Icon(Icons.save_outlined),
                  label: Text(isArabic ? 'حفظ' : 'Save'),
                ),
                const SizedBox(height: 12),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
