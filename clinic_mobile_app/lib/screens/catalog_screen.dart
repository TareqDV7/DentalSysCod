import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';

import '../models/treatment_procedure.dart';
import '../state/app_state.dart';

/// CRUD for the treatment-procedure catalog. Mirrors the desktop's
/// admin-side procedure list — same fields, same soft-delete semantics
/// (toggling `active` rather than hard-deleting, so historical follow-ups
/// that reference a procedure_id keep their link).
class CatalogScreen extends StatefulWidget {
  const CatalogScreen({super.key});

  @override
  State<CatalogScreen> createState() => _CatalogScreenState();
}

class _CatalogScreenState extends State<CatalogScreen> {
  List<TreatmentProcedure> _all = [];
  bool _loading = true;
  bool _showInactive = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final rows = await context.read<AppState>().catalog.getAll();
    if (!mounted) return;
    setState(() {
      _all = rows;
      _loading = false;
    });
  }

  Future<void> _addOrEdit({TreatmentProcedure? existing}) async {
    final app = context.read<AppState>();
    final result = await showModalBottomSheet<_ProcedureSheetResult>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) =>
          _ProcedureSheet(existing: existing, isArabic: app.isArabic),
    );
    if (result == null) return;
    if (existing == null) {
      await app.catalog.add(result.toProcedure());
    } else {
      await app.catalog.update(result.toProcedure(idOverride: existing.id));
    }
    if (mounted) await _load();
  }

  Future<void> _toggleActive(TreatmentProcedure p) async {
    final svc = context.read<AppState>().catalog;
    if (p.isActive) {
      await svc.deactivate(p);
    } else {
      await svc.reactivate(p);
    }
    if (mounted) await _load();
  }

  @override
  Widget build(BuildContext context) {
    final isArabic = context.select<AppState, bool>((s) => s.isArabic);
    final scheme = Theme.of(context).colorScheme;
    final shown = _all
        .where((p) => _showInactive ? true : p.isActive)
        .toList();
    return Scaffold(
      appBar: AppBar(
        title: Text(isArabic ? 'كتالوج الإجراءات' : 'Procedure catalog'),
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
                          ? 'لا توجد إجراءات بعد — أضف أول إجراء'
                          : 'No procedures yet — add your first one',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: scheme.onSurfaceVariant),
                    ),
                  ),
                )
              : RefreshIndicator(
                  onRefresh: _load,
                  child: ListView.separated(
                    padding: const EdgeInsets.all(16),
                    itemCount: shown.length,
                    separatorBuilder: (_, _) => const SizedBox(height: 8),
                    itemBuilder: (_, i) => _ProcedureTile(
                      procedure: shown[i],
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
        label: Text(isArabic ? 'إضافة إجراء' : 'Add procedure',
            style: const TextStyle(fontWeight: FontWeight.w700)),
      ),
    );
  }
}

class _ProcedureTile extends StatelessWidget {
  const _ProcedureTile({
    required this.procedure,
    required this.onEdit,
    required this.onToggleActive,
    required this.isArabic,
  });

  final TreatmentProcedure procedure;
  final VoidCallback onEdit;
  final VoidCallback onToggleActive;
  final bool isArabic;

  static final _fmt = NumberFormat('#,##0.00', 'en');

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final inactive = !procedure.isActive;
    return InkWell(
      borderRadius: BorderRadius.circular(14),
      onTap: onEdit,
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: inactive ? scheme.surfaceContainerHighest : scheme.surface,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: scheme.outlineVariant),
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    procedure.name,
                    style: TextStyle(
                      fontWeight: FontWeight.w700,
                      color: inactive ? scheme.onSurfaceVariant : null,
                      decoration:
                          inactive ? TextDecoration.lineThrough : null,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Wrap(
                    spacing: 12,
                    children: [
                      _meta(scheme,
                          '${isArabic ? "السعر" : "Price"}: ₪${_fmt.format(procedure.defaultPrice)}'),
                      if (procedure.requiresLab)
                        _meta(scheme,
                            '${isArabic ? "مختبر" : "Lab"}: ₪${_fmt.format(procedure.labExpense)}'),
                    ],
                  ),
                ],
              ),
            ),
            IconButton(
              tooltip: inactive
                  ? (isArabic ? 'إعادة التفعيل' : 'Reactivate')
                  : (isArabic ? 'إلغاء التفعيل' : 'Deactivate'),
              icon: Icon(inactive
                  ? Icons.restore
                  : Icons.archive_outlined),
              onPressed: onToggleActive,
            ),
          ],
        ),
      ),
    );
  }

  Widget _meta(ColorScheme scheme, String text) => Text(
        text,
        style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 12),
      );
}

class _ProcedureSheetResult {
  final String name;
  final double defaultPrice;
  final double labExpense;
  final bool requiresLab;
  final bool isActive;
  _ProcedureSheetResult({
    required this.name,
    required this.defaultPrice,
    required this.labExpense,
    required this.requiresLab,
    required this.isActive,
  });

  TreatmentProcedure toProcedure({int? idOverride}) => TreatmentProcedure(
        id: idOverride,
        name: name,
        defaultPrice: defaultPrice,
        labExpense: requiresLab ? labExpense : 0,
        requiresLab: requiresLab,
        isActive: isActive,
      );
}

class _ProcedureSheet extends StatefulWidget {
  const _ProcedureSheet({this.existing, required this.isArabic});
  final TreatmentProcedure? existing;
  final bool isArabic;

  @override
  State<_ProcedureSheet> createState() => _ProcedureSheetState();
}

class _ProcedureSheetState extends State<_ProcedureSheet> {
  late final TextEditingController _name;
  late final TextEditingController _price;
  late final TextEditingController _lab;
  bool _requiresLab = false;
  bool _isActive = true;

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    _name = TextEditingController(text: e?.name ?? '');
    _price = TextEditingController(
        text: (e?.defaultPrice ?? 0) == 0 ? '' : e!.defaultPrice.toString());
    _lab = TextEditingController(
        text: (e?.labExpense ?? 0) == 0 ? '' : e!.labExpense.toString());
    _requiresLab = e?.requiresLab ?? false;
    _isActive = e?.isActive ?? true;
  }

  @override
  void dispose() {
    _name.dispose();
    _price.dispose();
    _lab.dispose();
    super.dispose();
  }

  void _save() {
    final name = _name.text.trim();
    if (name.isEmpty) return;
    Navigator.of(context).pop(_ProcedureSheetResult(
      name: name,
      defaultPrice: double.tryParse(_price.text) ?? 0,
      labExpense: double.tryParse(_lab.text) ?? 0,
      requiresLab: _requiresLab,
      isActive: _isActive,
    ));
  }

  @override
  Widget build(BuildContext context) {
    final isArabic = widget.isArabic;
    final isEdit = widget.existing != null;
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
                      color: Theme.of(context).colorScheme.outlineVariant,
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ),
                ),
                Text(
                  isEdit
                      ? (isArabic ? 'تعديل إجراء' : 'Edit procedure')
                      : (isArabic ? 'إضافة إجراء' : 'Add procedure'),
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: _name,
                  textInputAction: TextInputAction.next,
                  decoration: InputDecoration(
                    labelText: isArabic ? 'اسم الإجراء' : 'Procedure name',
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _price,
                  keyboardType:
                      const TextInputType.numberWithOptions(decimal: true),
                  decoration: InputDecoration(
                    labelText: isArabic ? 'السعر الافتراضي' : 'Default price',
                    prefixText: '₪ ',
                  ),
                ),
                const SizedBox(height: 12),
                SwitchListTile.adaptive(
                  contentPadding: EdgeInsets.zero,
                  value: _requiresLab,
                  onChanged: (v) => setState(() => _requiresLab = v),
                  title: Text(isArabic
                      ? 'يتطلب مصاريف مختبر'
                      : 'Requires lab expense'),
                ),
                if (_requiresLab)
                  TextField(
                    controller: _lab,
                    keyboardType: const TextInputType.numberWithOptions(
                        decimal: true),
                    decoration: InputDecoration(
                      labelText: isArabic
                          ? 'مصاريف المختبر الافتراضية'
                          : 'Default lab expense',
                      prefixText: '₪ ',
                    ),
                  ),
                const SizedBox(height: 12),
                SwitchListTile.adaptive(
                  contentPadding: EdgeInsets.zero,
                  value: _isActive,
                  onChanged: (v) => setState(() => _isActive = v),
                  title: Text(isArabic ? 'مفعّل' : 'Active'),
                  subtitle: Text(isArabic
                      ? 'يظهر في قائمة الاختيار في زيارات المرضى'
                      : 'Shows up in the follow-up picker'),
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
