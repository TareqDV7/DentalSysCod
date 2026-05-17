import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';
import '../state/app_state.dart';
import '../utils/date_format_helper.dart';
import '../utils/app_strings.dart';
import '../models/patient.dart';
import '../models/followup.dart';
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
  List<Followup> _followups = [];
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
    final followups = await state.patients.getPatientFollowups(_patient.id!);
    final appts = await state.appointments.getPatientAppointments(_patient.id!);
    if (mounted) {
      setState(() {
        _followups = followups;
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

  void _addFollowup() {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _FollowupSheet(
        patientId: _patient.id!,
        onSaved: (f) async {
          final state = context.read<AppState>();
          await state.patients.addFollowup(f);
          // Fire-and-forget — keeps the save snappy; sync runs in background.
          unawaited(state.sync.syncNow());
          if (mounted) _load();
        },
      ),
    );
  }

  void _editFollowup(Followup followup) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _FollowupSheet(
        patientId: _patient.id!,
        existing: followup,
        onSaved: (f) async {
          final state = context.read<AppState>();
          await state.patients.updateFollowup(f);
          unawaited(state.sync.syncNow());
          if (mounted) _load();
        },
      ),
    );
  }

  Future<void> _deleteFollowup(Followup followup, Function(String) t) async {
    if (followup.id == null) return;
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
    if (confirm != true || !mounted) return;
    final state = context.read<AppState>();
    await state.patients
        .deleteFollowup(patientId: _patient.id!, id: followup.id!);
    unawaited(state.sync.syncNow());
    if (mounted) _load();
  }

  /// Patient's outstanding ledger balance = the last follow-up's running total
  /// (already cumulative). Negative values represent patient credit.
  double get _runningBalance =>
      _followups.isEmpty ? 0.0 : _followups.last.remainingAmount;

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
                            Text('${_followups.length}',
                                style: TextStyle(
                                    fontWeight: FontWeight.w800,
                                    color: scheme.primary,
                                    fontSize: 18)),
                            Text(t('visits'),
                                style: TextStyle(
                                    fontSize: 11,
                                    color: scheme.onSurfaceVariant)),
                            const SizedBox(height: 4),
                            Text('₪${fmt.format(_runningBalance)}',
                                style: TextStyle(
                                    fontWeight: FontWeight.w800,
                                    color: _runningBalance > 0
                                        ? const Color(0xFFD9434E)
                                        : _runningBalance < 0
                                            ? const Color(0xFF1F9A5F)
                                            : scheme.onSurfaceVariant,
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
                      _FollowupsTab(
                          followups: _followups,
                          onAdd: _addFollowup,
                          onEdit: _editFollowup,
                          onDelete: _deleteFollowup,
                          fmt: fmt),
                      _AppointmentsTab(appointments: _appointments),
                    ],
                  ),
          ),
        ],
      ),
    );
  }
}

class _FollowupsTab extends StatelessWidget {
  final List<Followup> followups;
  final VoidCallback onAdd;
  final void Function(Followup) onEdit;
  final Future<void> Function(Followup, String Function(String)) onDelete;
  final NumberFormat fmt;
  const _FollowupsTab({
    required this.followups,
    required this.onAdd,
    required this.onEdit,
    required this.onDelete,
    required this.fmt,
  });

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final isArabic = context.select<AppState, bool>((state) => state.isArabic);
    String t(String key) => AppStrings.t(key, isArabic: isArabic);
    if (followups.isEmpty) {
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
            itemCount: followups.length,
            itemBuilder: (_, i) {
              final f = followups[i];
              final parsedDate = DateFormatHelper.parseApiDate(f.followupDate);
              final dateDisplay = parsedDate != null
                  ? DateFormatHelper.formatDate(parsedDate)
                  : f.followupDate;
              final balanceColor = f.remainingAmount > 0
                  ? const Color(0xFFD9434E)
                  : f.remainingAmount < 0
                      ? const Color(0xFF1F9A5F)
                      : scheme.onSurface;
              return InkWell(
                onTap: () => onEdit(f),
                borderRadius: BorderRadius.circular(16),
                child: Container(
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
                            child: Text(
                              f.treatmentProcedure.isEmpty
                                  ? t('visit')
                                  : f.treatmentProcedure,
                              style:
                                  const TextStyle(fontWeight: FontWeight.w700),
                            ),
                          ),
                          Text(dateDisplay,
                              style: TextStyle(
                                  color: scheme.onSurfaceVariant, fontSize: 12)),
                        ],
                      ),
                      if ((f.toothNo ?? '').isNotEmpty) ...[
                        const SizedBox(height: 4),
                        Text('${t('tooth_no')}: ${f.toothNo}',
                            style: TextStyle(
                                color: scheme.onSurfaceVariant, fontSize: 12)),
                      ],
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          _col(t('price'), '₪${fmt.format(f.price)}', scheme),
                          _col(t('discount'), '₪${fmt.format(f.discount)}',
                              scheme),
                          _col(t('paid'), '₪${fmt.format(f.payment)}', scheme),
                          _col(t('balance'),
                              '₪${fmt.format(f.remainingAmount)}', scheme,
                              balanceColor),
                        ],
                      ),
                      const SizedBox(height: 4),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.end,
                        children: [
                          IconButton(
                            icon: const Icon(Icons.delete,
                                size: 18, color: Color(0xFFD9434E)),
                            onPressed: () => onDelete(f, t),
                            tooltip: t('delete'),
                          ),
                        ],
                      ),
                    ],
                  ),
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

class _FollowupSheet extends StatefulWidget {
  final int patientId;
  final Followup? existing;
  final Future<void> Function(Followup) onSaved;
  const _FollowupSheet({
    required this.patientId,
    required this.onSaved,
    this.existing,
  });

  @override
  State<_FollowupSheet> createState() => _FollowupSheetState();
}

class _FollowupSheetState extends State<_FollowupSheet> {
  final _procedure = TextEditingController();
  final _tooth = TextEditingController();
  final _price = TextEditingController();
  final _discount = TextEditingController();
  final _lab = TextEditingController();
  final _payment = TextEditingController();
  final _notes = TextEditingController();
  bool _saving = false;
  late String _date;

  bool get _isEdit => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    if (e != null) {
      _date = e.followupDate.isEmpty
          ? DateFormatHelper.formatDateForApi(DateTime.now())
          : e.followupDate;
      _procedure.text = e.treatmentProcedure;
      _tooth.text = e.toothNo ?? '';
      _price.text = e.price == 0 ? '' : e.price.toString();
      _discount.text = e.discount == 0 ? '' : e.discount.toString();
      _lab.text = e.labExpense == 0 ? '' : e.labExpense.toString();
      _payment.text = e.payment == 0 ? '' : e.payment.toString();
      _notes.text = e.notes ?? '';
    } else {
      _date = DateFormatHelper.formatDateForApi(DateTime.now());
    }
  }

  @override
  void dispose() {
    for (final c in [_procedure, _tooth, _price, _discount, _lab, _payment, _notes]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _pickDate() async {
    final current = DateFormatHelper.parseApiDate(_date) ?? DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: current,
      firstDate: DateTime(2000),
      lastDate: DateTime.now().add(const Duration(days: 365 * 5)),
    );
    if (picked != null) {
      setState(() => _date = DateFormatHelper.formatDateForApi(picked));
    }
  }

  Future<void> _save() async {
    if (_procedure.text.trim().isEmpty) return;
    setState(() => _saving = true);
    final existing = widget.existing;
    final f = Followup(
      id: existing?.id,
      patientId: widget.patientId,
      followupDate: _date,
      treatmentProcedure: _procedure.text.trim(),
      procedureId: existing?.procedureId,
      toothNo: _tooth.text.trim().isEmpty ? null : _tooth.text.trim(),
      price: double.tryParse(_price.text) ?? 0,
      discount: double.tryParse(_discount.text) ?? 0,
      labExpense: double.tryParse(_lab.text) ?? 0,
      payment: double.tryParse(_payment.text) ?? 0,
      remainingAmount: existing?.remainingAmount ?? 0,
      notes: _notes.text.trim().isEmpty ? null : _notes.text.trim(),
    );
    await widget.onSaved(f);
    if (mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    final isArabic = context.select<AppState, bool>((state) => state.isArabic);
    String t(String key) => AppStrings.t(key, isArabic: isArabic);
    final dateDisplay = DateFormatHelper.parseApiDate(_date) != null
        ? DateFormatHelper.formatDate(DateFormatHelper.parseApiDate(_date)!)
        : _date;
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
                Text(_isEdit ? t('edit_visit') : t('add_visit'),
                    style: Theme.of(context).textTheme.titleLarge),
                const Spacer(),
                IconButton(
                    onPressed: () => Navigator.pop(context),
                    icon: const Icon(Icons.close)),
              ]),
            ),
            Expanded(
              child: ListView(
                controller: scroll,
                padding: const EdgeInsets.all(16),
                children: [
                  InkWell(
                    onTap: _pickDate,
                    child: InputDecorator(
                      decoration: InputDecoration(
                        labelText: t('date'),
                        suffixIcon: const Icon(Icons.calendar_today_outlined),
                      ),
                      child: Text(dateDisplay,
                          style: const TextStyle(fontWeight: FontWeight.w600)),
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: _procedure,
                    decoration:
                        InputDecoration(labelText: t('procedure_treatment')),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: _tooth,
                    decoration: InputDecoration(labelText: t('tooth_no')),
                    keyboardType: TextInputType.text,
                  ),
                  const SizedBox(height: 12),
                  Row(children: [
                    Expanded(
                      child: TextField(
                        controller: _price,
                        decoration: InputDecoration(
                            labelText: '${t('price')} (₪)',
                            prefixText: '₪ '),
                        keyboardType: const TextInputType.numberWithOptions(
                            decimal: true),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: TextField(
                        controller: _discount,
                        decoration: InputDecoration(
                            labelText: '${t('discount')} (₪)',
                            prefixText: '₪ '),
                        keyboardType: const TextInputType.numberWithOptions(
                            decimal: true),
                      ),
                    ),
                  ]),
                  const SizedBox(height: 12),
                  Row(children: [
                    Expanded(
                      child: TextField(
                        controller: _lab,
                        decoration: InputDecoration(
                            labelText: '${t('lab_expense')} (₪)',
                            prefixText: '₪ '),
                        keyboardType: const TextInputType.numberWithOptions(
                            decimal: true),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: TextField(
                        controller: _payment,
                        decoration: InputDecoration(
                            labelText: '${t('payment_received')} (₪)',
                            prefixText: '₪ '),
                        keyboardType: const TextInputType.numberWithOptions(
                            decimal: true),
                      ),
                    ),
                  ]),
                  const SizedBox(height: 12),
                  TextField(
                      controller: _notes,
                      decoration: InputDecoration(labelText: t('notes')),
                      maxLines: 2),
                  const SizedBox(height: 20),
                  GradientButton(
                      label: t('save_visit'),
                      loading: _saving,
                      onPressed: _saving ? null : _save,
                      width: double.infinity),
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

