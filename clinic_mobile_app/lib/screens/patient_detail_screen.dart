import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';
import '../state/app_state.dart';
import '../utils/date_format_helper.dart';
import '../utils/app_strings.dart';
import '../models/patient.dart';
import '../models/visit.dart';
import '../models/appointment.dart';
import '../widgets/clinic_card.dart';
import '../widgets/status_badge.dart';
import '../widgets/empty_state.dart';
import '../widgets/gradient_button.dart';

class PatientDetailScreen extends StatefulWidget {
  final Patient patient;
  const PatientDetailScreen({super.key, required this.patient});

  @override
  State<PatientDetailScreen> createState() => _PatientDetailScreenState();
}

class _PatientDetailScreenState extends State<PatientDetailScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabs;
  List<Visit> _visits = [];
  List<Appointment> _appointments = [];
  bool _loading = true;
  bool _editing = false;
  late Patient _patient;

  late final _firstCtrl = TextEditingController(text: widget.patient.firstName);
  late final _lastCtrl = TextEditingController(text: widget.patient.lastName);
  late final _phoneCtrl = TextEditingController(text: widget.patient.phone ?? '');
  late final _historyCtrl = TextEditingController(text: widget.patient.medicalHistory ?? '');

  @override
  void initState() {
    super.initState();
    _patient = widget.patient;
    _tabs = TabController(length: 2, vsync: this);
    _load();
  }

  @override
  void dispose() {
    _tabs.dispose();
    for (final c in [_firstCtrl, _lastCtrl, _phoneCtrl, _historyCtrl]) { c.dispose(); }
    super.dispose();
  }

  Future<void> _load() async {
    final state = context.read<AppState>();
    final visits = await state.patients.getPatientVisits(_patient.id!);
    final appts = await state.appointments.getPatientAppointments(_patient.id!);
    if (mounted) {
      setState(() {
        _visits = visits;
        _appointments = appts;
        _loading = false;
      });
    }
  }

  Future<void> _saveEdit() async {
    final updated = _patient.copyWith(
      firstName: _firstCtrl.text.trim(),
      lastName: _lastCtrl.text.trim(),
      phone: _phoneCtrl.text.trim().isEmpty ? null : _phoneCtrl.text.trim(),
      medicalHistory: _historyCtrl.text.trim().isEmpty ? null : _historyCtrl.text.trim(),
    );
    final saved = await context.read<AppState>().patients.updatePatient(updated);
    if (mounted) {
      setState(() {
        _patient = saved;
        _editing = false;
      });
    }
  }

  void _addVisit() {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _AddVisitSheet(
        patientId: _patient.id!,
        patientName: _patient.fullName,
        onSaved: (v) async {
          await context.read<AppState>().patients.addVisit(v);
          if (mounted) _load();
        },
      ),
    );
  }

  void _editVisit(Visit visit, bool isArabic, Function(String) t) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _EditVisitSheet(
        patientId: _patient.id!,
        visit: visit,
        onSaved: (v) async {
          await context.read<AppState>().patients.updateVisit(_patient.id!, v);
          if (mounted) _load();
        },
      ),
    );
  }

  Future<void> _deleteVisit(Visit visit, int patientId, bool isArabic, Function(String) t) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(t('confirm_delete')),
        content: Text(t('delete_visit_confirm')),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: Text(t('cancel')),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: Text(t('delete'), style: const TextStyle(color: Color(0xFFD9434E))),
          ),
        ],
      ),
    );
    if (confirm == true && mounted && visit.id != null) {
      await context.read<AppState>().patients.deleteVisit(patientId, visit.id!);
      if (mounted) _load();
    }
  }

  double get _totalBalance =>
      _visits.fold(0, (sum, v) => sum + v.balance);

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final fmt = NumberFormat('#,##0.00', 'en');
    final isArabic = context.select<AppState, bool>((state) => state.isArabic);
    String t(String key) => AppStrings.t(key, isArabic: isArabic);

    return Scaffold(
      appBar: AppBar(
        title: Text(_patient.fullName),
        actions: [
          if (!_editing)
            IconButton(
                onPressed: () => setState(() => _editing = true),
                icon: const Icon(Icons.edit_outlined))
          else ...[
            TextButton(
                onPressed: () => setState(() => _editing = false),
                child: Text(t('cancel'),
                    style: const TextStyle(fontWeight: FontWeight.w700))),
            TextButton(
                onPressed: _saveEdit,
                child: Text(t('save'),
                    style: const TextStyle(fontWeight: FontWeight.w800))),
          ]
        ],
      ),
      body: Column(
        children: [
          // Header card
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
            child: ClinicCard(
              child: _editing
                  ? Column(children: [
                      Row(children: [
                        Expanded(
                            child: TextField(
                                controller: _firstCtrl,
                                decoration: InputDecoration(
                                    labelText: t('first_name')))),
                        const SizedBox(width: 12),
                        Expanded(
                            child: TextField(
                                controller: _lastCtrl,
                                decoration:
                                    InputDecoration(labelText: t('last_name')))),
                      ]),
                      const SizedBox(height: 12),
                      TextField(
                          controller: _phoneCtrl,
                          decoration: InputDecoration(labelText: t('phone')),
                          keyboardType: TextInputType.phone),
                      const SizedBox(height: 12),
                      TextField(
                          controller: _historyCtrl,
                          decoration:
                              InputDecoration(labelText: t('medical_history')),
                          maxLines: 2),
                    ])
                  : Row(
                      children: [
                        CircleAvatar(
                          radius: 28,
                          backgroundColor: scheme.primary.withAlpha(20),
                          child: Text(
                            '${_patient.firstName[0]}${_patient.lastName.isNotEmpty ? _patient.lastName[0] : ''}'
                                .toUpperCase(),
                            style: TextStyle(
                                color: scheme.primary,
                                fontWeight: FontWeight.w800,
                                fontSize: 18),
                          ),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(_patient.fullName,
                                  style: const TextStyle(
                                      fontWeight: FontWeight.w800, fontSize: 16)),
                              if (_patient.phone != null)
                                Text(_patient.phone!,
                                    style: TextStyle(
                                        color: scheme.onSurfaceVariant,
                                        fontSize: 13)),
                              if (_patient.medicalHistory != null)
                                Text(_patient.medicalHistory!,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: TextStyle(
                                        color: scheme.onSurfaceVariant,
                                        fontSize: 12)),
                            ],
                          ),
                        ),
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.end,
                          children: [
                            Text('${_visits.length}',
                                style: TextStyle(
                                    fontWeight: FontWeight.w800,
                                    color: scheme.primary,
                                    fontSize: 18)),
                            Text(t('visits'),
                                style: TextStyle(
                                    fontSize: 11,
                                    color: scheme.onSurfaceVariant)),
                            const SizedBox(height: 4),
                            Text('₪${fmt.format(_totalBalance)}',
                                style: const TextStyle(
                                    fontWeight: FontWeight.w800,
                                    color: Color(0xFFD9434E),
                                    fontSize: 13)),
                            Text(t('balance'),
                                style: TextStyle(
                                    fontSize: 11,
                                    color: scheme.onSurfaceVariant)),
                          ],
                        ),
                      ],
                    ),
            ),
          ),

          TabBar(
            controller: _tabs,
            indicatorColor: scheme.primary,
            labelColor: scheme.primary,
            unselectedLabelColor: scheme.onSurfaceVariant,
            tabs: [Tab(text: t('follow_ups')), Tab(text: t('appointments'))],
          ),

          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : TabBarView(
                    controller: _tabs,
                    children: [
                      _VisitsTab(
                          visits: _visits,
                          onAdd: _addVisit,
                          fmt: fmt,
                          patientId: _patient.id!,
                          onEdit: _editVisit,
                          onDelete: _deleteVisit),
                      _AppointmentsTab(appointments: _appointments),
                    ],
                  ),
          ),
        ],
      ),
    );
  }
}

class _VisitsTab extends StatelessWidget {
  final List<Visit> visits;
  final VoidCallback onAdd;
  final NumberFormat fmt;
  final int patientId;
  final Function(Visit, bool, Function(String))? onEdit;
  final Function(Visit, int, bool, Function(String))? onDelete;
  const _VisitsTab(
      {required this.visits,
      required this.onAdd,
      required this.fmt,
      this.patientId = 0,
      this.onEdit,
      this.onDelete});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final isArabic = context.select<AppState, bool>((state) => state.isArabic);
    String t(String key) => AppStrings.t(key, isArabic: isArabic);
    if (visits.isEmpty) {
      return EmptyState(
        icon: Icons.receipt_long_outlined,
        message: t('no_followups'),
        actionLabel: t('add_visit'),
        onAction: onAdd,
      );
    }
    return Column(
      children: [
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: visits.length,
            itemBuilder: (_, i) {
              final v = visits[i];
              final parsedVisitDate = DateFormatHelper.parseApiDate(v.visitDate);
              final visitDateDisplay = parsedVisitDate != null
                  ? DateFormatHelper.formatDate(parsedVisitDate)
                  : v.visitDate;
              return Container(
                margin: const EdgeInsets.only(bottom: 8),
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: scheme.surface,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: scheme.outlineVariant),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Expanded(
                          child: Text(v.procedureName ?? t('visit'),
                              style: const TextStyle(fontWeight: FontWeight.w700)),
                        ),
                        Text(visitDateDisplay,
                            style: TextStyle(
                                color: scheme.onSurfaceVariant, fontSize: 12)),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        _col(t('price'), '₪${fmt.format(v.price ?? 0)}', scheme),
                        _col(t('lab'), '₪${fmt.format(v.labExpense ?? 0)}', scheme),
                        _col(t('paid'), '₪${fmt.format(v.payment ?? 0)}', scheme),
                        _col(t('balance'),
                            '₪${fmt.format(v.balance)}',
                            scheme,
                            v.balance > 0
                                ? const Color(0xFFD9434E)
                                : const Color(0xFF1F9A5F)),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.end,
                      children: [
                        IconButton(
                          icon: const Icon(Icons.edit, size: 18),
                          onPressed: v.id != null && onEdit != null
                              ? () => onEdit!(v, isArabic, t)
                              : null,
                          tooltip: t('edit'),
                        ),
                        IconButton(
                          icon: const Icon(Icons.delete,
                              size: 18, color: Color(0xFFD9434E)),
                          onPressed: v.id != null && onDelete != null
                              ? () => onDelete!(v, patientId, isArabic, t)
                              : null,
                          tooltip: t('delete'),
                        ),
                      ],
                    ),
                  ],
                ),
              );
            },
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
          child: GradientButton(
            label: t('add_visit'),
            icon: Icons.add,
            onPressed: onAdd,
            width: double.infinity,
          ),
        ),
      ],
    );
  }

  Widget _col(String label, String value, ColorScheme scheme,
      [Color? valueColor]) {
    return Expanded(
      child: Column(
        children: [
          Text(value,
              style: TextStyle(
                  fontWeight: FontWeight.w700,
                  fontSize: 13,
                  color: valueColor ?? scheme.onSurface)),
          Text(label,
              style: TextStyle(
                  fontSize: 10, color: scheme.onSurfaceVariant)),
        ],
      ),
    );
  }
}

class _AppointmentsTab extends StatelessWidget {
  final List<Appointment> appointments;
  const _AppointmentsTab({required this.appointments});

  @override
  Widget build(BuildContext context) {
    final isArabic = context.select<AppState, bool>((state) => state.isArabic);
    String t(String key) => AppStrings.t(key, isArabic: isArabic);
    if (appointments.isEmpty) {
      return EmptyState(
        icon: Icons.calendar_today_outlined,
        message: t('no_appointments'),
      );
    }
    final scheme = Theme.of(context).colorScheme;
    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: appointments.length,
      itemBuilder: (_, i) {
        final a = appointments[i];
        final dt = a.dateTime;
        return Container(
          margin: const EdgeInsets.only(bottom: 8),
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: scheme.surface,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: scheme.outlineVariant),
          ),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('${DateFormatHelper.formatDate(dt)} (${DateFormat('EEEE').format(dt)})',
                        style: const TextStyle(fontWeight: FontWeight.w700)),
                    Text(DateFormat('h:mm a').format(dt),
                        style: TextStyle(
                            color: scheme.onSurfaceVariant, fontSize: 13)),
                    if (a.treatmentType != null)
                      Text(a.treatmentType!,
                          style: TextStyle(
                              color: scheme.onSurfaceVariant, fontSize: 12)),
                  ],
                ),
              ),
              StatusBadge(a.status),
            ],
          ),
        );
      },
    );
  }
}

class _AddVisitSheet extends StatefulWidget {
  final int patientId;
  final String patientName;
  final Future<void> Function(Visit) onSaved;
  const _AddVisitSheet(
      {required this.patientId,
      required this.patientName,
      required this.onSaved});

  @override
  State<_AddVisitSheet> createState() => _AddVisitSheetState();
}

class _AddVisitSheetState extends State<_AddVisitSheet> {
  final _procedure = TextEditingController();
  final _price = TextEditingController();
  final _lab = TextEditingController();
  final _payment = TextEditingController();
  final _notes = TextEditingController();
  bool _saving = false;
  late String _date;
  
  @override
  void initState() {
    super.initState();
    _date = DateFormatHelper.formatDateForApi(DateTime.now());
  }

  @override
  void dispose() {
    for (final c in [_procedure, _price, _lab, _payment, _notes]) { c.dispose(); }
    super.dispose();
  }

  Future<void> _save() async {
    if (_procedure.text.trim().isEmpty) return;
    setState(() => _saving = true);
    await widget.onSaved(Visit(
      patientId: widget.patientId,
      patientName: widget.patientName,
      visitDate: _date,
      procedureName: _procedure.text.trim(),
      price: double.tryParse(_price.text),
      labExpense: double.tryParse(_lab.text),
      payment: double.tryParse(_payment.text),
      notes: _notes.text.trim().isEmpty ? null : _notes.text.trim(),
    ));
    if (mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    final isArabic = context.select<AppState, bool>((state) => state.isArabic);
    String t(String key) => AppStrings.t(key, isArabic: isArabic);
    return DraggableScrollableSheet(
      initialChildSize: 0.85,
      minChildSize: 0.5,
      maxChildSize: 0.95,
      builder: (_, scroll) => Container(
        decoration: BoxDecoration(
          color: Theme.of(context).scaffoldBackgroundColor,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
        ),
        child: Column(
          children: [
            const SizedBox(height: 8),
            Container(
              width: 40, height: 4,
              decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.outlineVariant,
                  borderRadius: BorderRadius.circular(2)),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
              child: Row(children: [
                Text(t('add_visit'), style: Theme.of(context).textTheme.titleLarge),
                const Spacer(),
                IconButton(onPressed: () => Navigator.pop(context), icon: const Icon(Icons.close)),
              ]),
            ),
            Expanded(
              child: ListView(
                controller: scroll,
                padding: const EdgeInsets.all(16),
                children: [
                  TextField(
                    controller: _procedure,
                    decoration: InputDecoration(labelText: t('procedure_treatment')),
                  ),
                  const SizedBox(height: 12),
                  Row(children: [
                    Expanded(child: TextField(controller: _price, decoration: InputDecoration(labelText: '${t('price')} (₪)', prefixText: '₪ '), keyboardType: TextInputType.number)),
                    const SizedBox(width: 12),
                    Expanded(child: TextField(controller: _lab, decoration: InputDecoration(labelText: '${t('lab_expense')} (₪)', prefixText: '₪ '), keyboardType: TextInputType.number)),
                  ]),
                  const SizedBox(height: 12),
                  TextField(controller: _payment, decoration: InputDecoration(labelText: '${t('payment_received')} (₪)', prefixText: '₪ '), keyboardType: TextInputType.number),
                  const SizedBox(height: 12),
                  TextField(controller: _notes, decoration: InputDecoration(labelText: t('notes')), maxLines: 2),
                  const SizedBox(height: 20),
                  GradientButton(label: t('save_visit'), loading: _saving, onPressed: _saving ? null : _save, width: double.infinity),
                  const SizedBox(height: 16),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _EditVisitSheet extends StatefulWidget {
  final int patientId;
  final Visit visit;
  final Future<void> Function(Visit) onSaved;
  const _EditVisitSheet(
      {required this.patientId,
      required this.visit,
      required this.onSaved});

  @override
  State<_EditVisitSheet> createState() => _EditVisitSheetState();
}

class _EditVisitSheetState extends State<_EditVisitSheet> {
  final _procedure = TextEditingController();
  final _price = TextEditingController();
  final _lab = TextEditingController();
  final _payment = TextEditingController();
  final _notes = TextEditingController();
  bool _saving = false;
  late String _date;
  
  @override
  void initState() {
    super.initState();
    _date = widget.visit.visitDate;
    _procedure.text = widget.visit.procedureName ?? '';
    _price.text = widget.visit.price?.toString() ?? '';
    _lab.text = widget.visit.labExpense?.toString() ?? '';
    _payment.text = widget.visit.payment?.toString() ?? '';
    _notes.text = widget.visit.notes ?? '';
  }

  @override
  void dispose() {
    for (final c in [_procedure, _price, _lab, _payment, _notes]) { c.dispose(); }
    super.dispose();
  }

  Future<void> _save() async {
    if (_procedure.text.trim().isEmpty) return;
    setState(() => _saving = true);
    await widget.onSaved(Visit(
      id: widget.visit.id,
      patientId: widget.visit.patientId,
      patientName: widget.visit.patientName,
      visitDate: _date,
      procedureName: _procedure.text.trim(),
      price: double.tryParse(_price.text),
      labExpense: double.tryParse(_lab.text),
      payment: double.tryParse(_payment.text),
      notes: _notes.text.trim().isEmpty ? null : _notes.text.trim(),
      updatedAt: widget.visit.updatedAt,
    ));
    if (mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    final isArabic = context.select<AppState, bool>((state) => state.isArabic);
    String t(String key) => AppStrings.t(key, isArabic: isArabic);
    return DraggableScrollableSheet(
      initialChildSize: 0.85,
      minChildSize: 0.5,
      maxChildSize: 0.95,
      builder: (_, scroll) => Container(
        decoration: BoxDecoration(
          color: Theme.of(context).scaffoldBackgroundColor,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
        ),
        child: Column(
          children: [
            const SizedBox(height: 8),
            Container(
              width: 40, height: 4,
              decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.outlineVariant,
                  borderRadius: BorderRadius.circular(2)),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
              child: Row(children: [
                Text(t('edit_visit'), style: Theme.of(context).textTheme.titleLarge),
                const Spacer(),
                IconButton(onPressed: () => Navigator.pop(context), icon: const Icon(Icons.close)),
              ]),
            ),
            Expanded(
              child: ListView(
                controller: scroll,
                padding: const EdgeInsets.all(16),
                children: [
                  TextField(
                    controller: _procedure,
                    decoration: InputDecoration(labelText: t('procedure_treatment')),
                  ),
                  const SizedBox(height: 12),
                  Row(children: [
                    Expanded(child: TextField(controller: _price, decoration: InputDecoration(labelText: '${t('price')} (₪)', prefixText: '₪ '), keyboardType: TextInputType.number)),
                    const SizedBox(width: 12),
                    Expanded(child: TextField(controller: _lab, decoration: InputDecoration(labelText: '${t('lab_expense')} (₪)', prefixText: '₪ '), keyboardType: TextInputType.number)),
                  ]),
                  const SizedBox(height: 12),
                  TextField(controller: _payment, decoration: InputDecoration(labelText: '${t('payment_received')} (₪)', prefixText: '₪ '), keyboardType: TextInputType.number),
                  const SizedBox(height: 12),
                  TextField(controller: _notes, decoration: InputDecoration(labelText: t('notes')), maxLines: 2),
                  const SizedBox(height: 20),
                  GradientButton(label: t('save_visit'), loading: _saving, onPressed: _saving ? null : _save, width: double.infinity),
                  const SizedBox(height: 16),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
