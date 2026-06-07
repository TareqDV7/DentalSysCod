import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:table_calendar/table_calendar.dart';
import 'package:intl/intl.dart';
import '../state/app_state.dart';
import '../models/appointment.dart';
import '../models/patient.dart';
import '../services/connectivity_sync_service.dart';
import '../models/treatment_procedure.dart';
import '../models/followup.dart';
import '../widgets/status_badge.dart';
import '../widgets/empty_state.dart';
import '../widgets/gradient_button.dart';
import '../utils/app_strings.dart';
import '../utils/date_format_helper.dart';

class AppointmentsScreen extends StatefulWidget {
  const AppointmentsScreen({super.key});

  @override
  State<AppointmentsScreen> createState() => _AppointmentsScreenState();
}

class _AppointmentsScreenState extends State<AppointmentsScreen> {
  DateTime _focusedDay = DateTime.now();
  DateTime _selectedDay = DateTime.now();
  Map<DateTime, int> _counts = {};
  List<Appointment> _dayAppointments = [];
  bool _loading = true;
  StreamSubscription<SyncStatus>? _syncSub;

  void _showMessage(String message, {bool isError = false}) {
    if (!mounted) return;
    final scheme = Theme.of(context).colorScheme;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: isError ? scheme.error : null,
      ),
    );
  }

  @override
  void initState() {
    super.initState();
    _loadMonth(_focusedDay);
    _loadDay(_selectedDay);
    // Kept alive in the home IndexedStack, so initState runs once. Refresh the
    // visible month + day whenever a background sync completes, so synced
    // appointments (and their now-resolved patient names) show up.
    _syncSub = context.read<AppState>().sync.statusStream.listen((status) {
      if (status == SyncStatus.synced && mounted) {
        _loadMonth(_focusedDay);
        _loadDay(_selectedDay, silent: true);
      }
    });
  }

  @override
  void dispose() {
    _syncSub?.cancel();
    super.dispose();
  }

  Future<void> _loadMonth(DateTime month) async {
    final counts = await context
        .read<AppState>()
        .appointments
        .getMonthCounts(month.year, month.month);
    if (mounted) setState(() => _counts = counts);
  }

  Future<void> _loadDay(DateTime day, {bool silent = false}) async {
    if (!silent) setState(() => _loading = true);
    final appts = await context
        .read<AppState>()
        .appointments
        .getAppointments(date: day);
    if (mounted) setState(() { _dayAppointments = appts; _loading = false; });
  }

  void _onDaySelected(DateTime selected, DateTime focused) {
    setState(() {
      _selectedDay = selected;
      _focusedDay = focused;
    });
    _loadDay(selected);
  }

  void _onPageChanged(DateTime focused) {
    _focusedDay = focused;
    _loadMonth(focused);
  }

  bool _isFriday(DateTime day) => day.weekday == DateTime.friday;

  void _addAppointment() {
    final ar = context.read<AppState>().isArabic;
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _AddAppointmentSheet(
        initialDate: _selectedDay,
        onSaved: (a) async {
          try {
            await context.read<AppState>().appointments.addAppointment(a);
            if (mounted) {
              _loadDay(_selectedDay);
              _loadMonth(_focusedDay);
              _showMessage(AppStrings.t('appointment_saved', isArabic: ar));
            }
          } catch (error) {
            _showMessage(error.toString(), isError: true);
            rethrow;
          }
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final ar = context.watch<AppState>().isArabic;

    return Scaffold(
      body: Column(
        children: [
          // Calendar
          TableCalendar(
            firstDay: DateTime(2020),
            lastDay: DateTime(2030),
            focusedDay: _focusedDay,
            selectedDayPredicate: (day) => isSameDay(day, _selectedDay),
            onDaySelected: _onDaySelected,
            onPageChanged: _onPageChanged,
            enabledDayPredicate: (day) => !_isFriday(day),
            calendarStyle: CalendarStyle(
              selectedDecoration: BoxDecoration(
                color: scheme.primary,
                shape: BoxShape.circle,
              ),
              todayDecoration: BoxDecoration(
                color: scheme.primary.withAlpha(40),
                shape: BoxShape.circle,
              ),
              todayTextStyle: TextStyle(
                  color: scheme.primary, fontWeight: FontWeight.w800),
              disabledTextStyle: TextStyle(
                  color: scheme.onSurface.withAlpha(50)),
              weekendTextStyle: TextStyle(color: scheme.error),
              markerDecoration: BoxDecoration(
                color: scheme.secondary,
                shape: BoxShape.circle,
              ),
            ),
            headerStyle: HeaderStyle(
              formatButtonVisible: false,
              titleCentered: true,
              titleTextStyle: TextStyle(
                  fontWeight: FontWeight.w800, color: scheme.onSurface),
            ),
            calendarBuilders: CalendarBuilders(
              markerBuilder: (context, day, events) {
                final key = DateTime(day.year, day.month, day.day);
                final count = _counts[key] ?? 0;
                if (count == 0) return null;
                return Positioned(
                  bottom: 2,
                  child: Container(
                    width: 6,
                    height: 6,
                    decoration: BoxDecoration(
                        color: scheme.secondary, shape: BoxShape.circle),
                  ),
                );
              },
              disabledBuilder: (context, day, focusedDay) {
                return Center(
                  child: Text(
                    '${day.day}',
                    style: TextStyle(
                        color: scheme.onSurface.withAlpha(40), fontSize: 13),
                  ),
                );
              },
            ),
          ),

          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Row(
              children: [
                Text(
                  '${DateFormat('EEEE').format(_selectedDay)}, ${DateFormatHelper.formatDate(_selectedDay)}',
                  style: const TextStyle(fontWeight: FontWeight.w800),
                ),
                const Spacer(),
                if (_isFriday(_selectedDay))
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: scheme.errorContainer,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(AppStrings.t('holiday', isArabic: ar),
                        style: TextStyle(
                            color: scheme.error,
                            fontSize: 12,
                            fontWeight: FontWeight.w700)),
                  ),
              ],
            ),
          ),

          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _dayAppointments.isEmpty
                    ? EmptyState(
                        icon: Icons.calendar_today_outlined,
                        message: _isFriday(_selectedDay)
                            ? AppStrings.t('friday_closed', isArabic: ar)
                            : AppStrings.t('no_appointments_on_day',
                                isArabic: ar),
                        actionLabel: _isFriday(_selectedDay)
                            ? null
                            : AppStrings.t('add_appointment', isArabic: ar),
                        onAction:
                            _isFriday(_selectedDay) ? null : _addAppointment,
                      )
                    : RefreshIndicator(
                        onRefresh: () => _loadDay(_selectedDay),
                        child: ListView.builder(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 16, vertical: 4),
                          itemCount: _dayAppointments.length,
                          itemBuilder: (_, i) => _AppointmentTile(
                            appointment: _dayAppointments[i],
                            onChanged: () => _loadDay(_selectedDay),
                          ),
                        ),
                      ),
          ),
        ],
      ),
      floatingActionButton: _isFriday(_selectedDay)
          ? null
          : FloatingActionButton.extended(
              onPressed: _addAppointment,
              backgroundColor: scheme.primary,
              foregroundColor: Colors.white,
              icon: const Icon(Icons.add),
              label: Text(AppStrings.t('add', isArabic: ar),
                  style: const TextStyle(fontWeight: FontWeight.w700)),
            ),
    );
  }
}

class _AppointmentTile extends StatelessWidget {
  final Appointment appointment;
  final VoidCallback? onChanged;
  const _AppointmentTile({required this.appointment, this.onChanged});

  static const _statuses = <String>[
    'scheduled',
    'completed',
    'postponed',
    'pending',
  ];

  String _safePatientName(bool isArabic) {
    final fallback =
        '${AppStrings.t('patient', isArabic: isArabic)} #${appointment.patientId}';
    final raw = appointment.patientName?.trim();
    if (raw == null || raw.isEmpty) {
      return fallback;
    }
    final lowered = raw.toLowerCase();
    if (lowered == 'null' || lowered == 'undefined') {
      return fallback;
    }
    return raw;
  }

  Future<void> _showActions(BuildContext context) async {
    final id = appointment.id;
    if (id == null) return;
    final app = context.read<AppState>();
    final isArabic = app.isArabic;
    final picked = await showModalBottomSheet<String>(
      context: context,
      builder: (sheetCtx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
              child: Align(
                alignment: AlignmentDirectional.centerStart,
                child: Text(
                  isArabic ? 'حالة الموعد' : 'Appointment status',
                  style: Theme.of(sheetCtx).textTheme.titleMedium,
                ),
              ),
            ),
            for (final s in _statuses)
              ListTile(
                leading: Icon(
                  s == appointment.status
                      ? Icons.radio_button_checked
                      : Icons.radio_button_off,
                  color: s == appointment.status
                      ? Theme.of(sheetCtx).colorScheme.primary
                      : null,
                ),
                title: Text(_statusLabel(s, isArabic)),
                onTap: () => Navigator.pop(sheetCtx, s),
              ),
            const Divider(height: 1),
            ListTile(
              leading: const Icon(Icons.medical_services_outlined),
              title: Text(
                  isArabic ? 'تحويل إلى زيارة' : 'Convert to follow-up'),
              subtitle: Text(isArabic
                  ? 'إنشاء سجل متابعة ووضع علامة مكتمل'
                  : 'Creates a follow-up entry and marks completed'),
              onTap: () => Navigator.pop(sheetCtx, '__convert__'),
            ),
            const Divider(height: 1),
            ListTile(
              leading: const Icon(Icons.delete_outline, color: Color(0xFFD9434E)),
              title: Text(isArabic ? 'حذف الموعد' : 'Delete appointment',
                  style: const TextStyle(color: Color(0xFFD9434E))),
              onTap: () => Navigator.pop(sheetCtx, '__delete__'),
            ),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
    if (picked == null) return;
    if (!context.mounted) return;

    if (picked == '__delete__') {
      await app.appointments.deleteAppointment(id);
      onChanged?.call();
      return;
    }

    if (picked == '__convert__') {
      try {
        await app.patients.addFollowup(Followup(
          patientId: appointment.patientId,
          followupDate: DateFormatHelper.formatDateForApi(appointment.dateTime),
          treatmentProcedure: (appointment.treatmentType == null ||
                  appointment.treatmentType!.trim().isEmpty)
              ? (isArabic ? 'زيارة' : 'Visit')
              : appointment.treatmentType!,
        ));
        await app.appointments.updateStatus(id, 'completed');
        unawaited(app.sync.syncNow());
        onChanged?.call();
        if (context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(
              content: Text(isArabic
                  ? 'تم إنشاء سجل المتابعة'
                  : 'Follow-up created from appointment')));
        }
      } catch (e) {
        if (context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(
              content: Text(isArabic
                  ? 'تعذّر التحويل: $e'
                  : 'Could not convert: $e')));
        }
      }
      return;
    }
    if (picked != appointment.status) {
      try {
        await app.appointments.updateStatus(id, picked);
        onChanged?.call();
      } catch (e) {
        if (context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(
              content: Text(isArabic
                  ? 'تعذّر تحديث الحالة: $e'
                  : 'Could not update status: $e')));
        }
      }
    }
  }

  static String _statusLabel(String s, bool isArabic) {
    if (isArabic) {
      switch (s) {
        case 'scheduled': return 'مجدول';
        case 'completed': return 'مكتمل';
        case 'postponed': return 'مؤجل';
        case 'pending': return 'معلق';
        default: return s;
      }
    }
    return s[0].toUpperCase() + s.substring(1);
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final isArabic = context.watch<AppState>().isArabic;
    final dt = appointment.dateTime;

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      decoration: BoxDecoration(
        color: scheme.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: scheme.outlineVariant),
      ),
      child: Material(
        color: Colors.transparent,
        borderRadius: BorderRadius.circular(16),
        child: InkWell(
          borderRadius: BorderRadius.circular(16),
          onTap: () => _showActions(context),
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Row(
              children: [
                Container(
                  width: 48,
                  padding: const EdgeInsets.symmetric(vertical: 6),
                  decoration: BoxDecoration(
                    color: scheme.primary.withAlpha(15),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Column(
                    children: [
                      Text(DateFormat('h:mm').format(dt),
                          style: TextStyle(
                              fontWeight: FontWeight.w800,
                              fontSize: 13,
                              color: scheme.primary)),
                      Text(DateFormat('a').format(dt),
                          style:
                              TextStyle(fontSize: 10, color: scheme.primary)),
                    ],
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(_safePatientName(isArabic),
                          style: const TextStyle(fontWeight: FontWeight.w700)),
                      if (appointment.treatmentType != null)
                        Text(appointment.treatmentType!,
                            style: TextStyle(
                                color: scheme.onSurfaceVariant, fontSize: 13)),
                      if (appointment.durationMinutes != null)
                        Text('${appointment.durationMinutes} ${AppStrings.t('minutes_short', isArabic: isArabic)}',
                            style: TextStyle(
                                color: scheme.onSurfaceVariant, fontSize: 12)),
                    ],
                  ),
                ),
                StatusBadge(appointment.status),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _AddAppointmentSheet extends StatefulWidget {
  final DateTime initialDate;
  final Future<void> Function(Appointment) onSaved;
  const _AddAppointmentSheet(
      {required this.initialDate, required this.onSaved});

  @override
  State<_AddAppointmentSheet> createState() => _AddAppointmentSheetState();
}

class _AddAppointmentSheetState extends State<_AddAppointmentSheet> {
  final _durationCtrl = TextEditingController(text: '30');
  final _notesCtrl = TextEditingController();
  
  // State variables
  Patient? _patient;
  List<Patient> _patients = [];
  TreatmentProcedure? _selectedTreatment;
  List<TreatmentProcedure> _treatments = [];
  String _selectedStatus = 'scheduled';
  late DateTime _dateTime;
  bool _saving = false;
  bool _loadingData = true;
  String? _loadError;

  void _showError(String message) {
    if (!mounted) return;
    final scheme = Theme.of(context).colorScheme;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: scheme.error,
      ),
    );
  }

  @override
  void initState() {
    super.initState();
    _dateTime = widget.initialDate.copyWith(
        hour: 9, minute: 0, second: 0, millisecond: 0);
    _loadData();
  }

  Future<void> _loadData() async {
    setState(() => _loadingData = true);
    final ar = context.read<AppState>().isArabic;
    try {
      final [patients, procedures] = await Future.wait([
        context.read<AppState>().patients.getPatients(),
        context.read<AppState>().db.getProcedures(),
      ]);
      if (mounted) {
        setState(() {
          _patients = patients as List<Patient>;
          _treatments = (procedures as List<TreatmentProcedure>)
              .where((p) => p.isActive)
              .toList();
          _loadingData = false;
        });
      }
    } catch (error) {
      if (mounted) {
        setState(() {
          _loadError = AppStrings.t('failed_to_load_data', isArabic: ar);
          _loadingData = false;
        });
      }
    }
  }

  Future<void> _pickDateTime() async {
    final date = await showDatePicker(
      context: context,
      initialDate: _dateTime,
      firstDate: DateTime.now().subtract(const Duration(days: 1)),
      lastDate: DateTime(2030),
      selectableDayPredicate: (d) => d.weekday != DateTime.friday,
    );
    if (date == null || !mounted) return;
    final time = await showTimePicker(
        context: context,
        initialTime: TimeOfDay.fromDateTime(_dateTime));
    if (time == null) return;
    setState(() => _dateTime =
        date.copyWith(hour: time.hour, minute: time.minute));
  }

  Future<void> _save() async {
    if (_patient == null || _selectedTreatment == null) {
      _showError(AppStrings.t('select_patient_treatment',
          isArabic: context.read<AppState>().isArabic));
      return;
    }
    setState(() => _saving = true);
    try {
      await widget.onSaved(Appointment(
        patientId: _patient!.id!,
        patientName: _patient!.fullName,
        appointmentDatetime: _dateTime.toIso8601String(),
        durationMinutes: int.tryParse(_durationCtrl.text),
        treatmentType: _selectedTreatment!.name,
        status: _selectedStatus,
        notes: _notesCtrl.text.trim().isEmpty ? null : _notesCtrl.text.trim(),
      ));
      if (mounted) Navigator.pop(context);
    } catch (error) {
      _showError(error.toString());
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  void dispose() {
    _durationCtrl.dispose();
    _notesCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final ar = context.watch<AppState>().isArabic;

    return DraggableScrollableSheet(
      initialChildSize: 0.85,
      minChildSize: 0.5,
      maxChildSize: 0.95,
      builder: (_, scroll) => Container(
        decoration: BoxDecoration(
          color: Theme.of(context).scaffoldBackgroundColor,
          borderRadius:
              const BorderRadius.vertical(top: Radius.circular(24)),
        ),
        child: SafeArea(
          top: false,
          child: Column(
            children: [
              const SizedBox(height: 8),
              Container(
                width: 40, height: 4,
                decoration: BoxDecoration(
                    color: scheme.outlineVariant,
                    borderRadius: BorderRadius.circular(2)),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
                child: Row(children: [
                  Text(AppStrings.t('add_appointment', isArabic: ar),
                      style: Theme.of(context).textTheme.titleLarge),
                  const Spacer(),
                  IconButton(
                      onPressed: () => Navigator.pop(context),
                      icon: const Icon(Icons.close)),
                ]),
              ),
              Expanded(
                child: _loadingData
                    ? const Center(child: CircularProgressIndicator())
                    : _loadError != null
                        ? Center(
                            child: Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Icon(Icons.error_outline,
                                    size: 48, color: scheme.error),
                                const SizedBox(height: 16),
                                Text(_loadError!,
                                    style: TextStyle(color: scheme.error)),
                                const SizedBox(height: 16),
                                GradientButton(
                                  label: AppStrings.t('retry', isArabic: ar),
                                  onPressed: _loadData,
                                  width: 120,
                                ),
                              ],
                            ),
                          )
                        : ListView(
                            controller: scroll,
                            padding: const EdgeInsets.all(16),
                            children: [
                              // ─────────────────────────────────────
                              // PATIENT & APPOINTMENT SECTION
                              // ─────────────────────────────────────
                              Text(AppStrings.t('patient_schedule', isArabic: ar),
                                  style: Theme.of(context)
                                      .textTheme
                                      .labelLarge
                                      ?.copyWith(
                                          color: scheme.primary,
                                          fontWeight: FontWeight.w700)),
                              const SizedBox(height: 12),
                              DropdownButtonFormField<Patient>(
                                initialValue: _patient,
                                decoration: InputDecoration(
                                  labelText:
                                      '${AppStrings.t('patient', isArabic: ar)} *',
                                  border: OutlineInputBorder(
                                      borderRadius:
                                          BorderRadius.circular(12)),
                                  contentPadding:
                                      const EdgeInsets.symmetric(
                                          horizontal: 16, vertical: 14),
                                ),
                                items: _patients
                                    .map((p) => DropdownMenuItem(
                                        value: p,
                                        child: Text(p.fullName)))
                                    .toList(),
                                onChanged: (p) =>
                                    setState(() => _patient = p),
                              ),
                              const SizedBox(height: 14),
                              InkWell(
                                onTap: _pickDateTime,
                                borderRadius: BorderRadius.circular(12),
                                child: Container(
                                  padding: const EdgeInsets.symmetric(
                                      horizontal: 16, vertical: 14),
                                  decoration: BoxDecoration(
                                    border:
                                        Border.all(color: scheme.outline),
                                    borderRadius:
                                        BorderRadius.circular(12),
                                  ),
                                  child: Row(
                                    children: [
                                      Expanded(
                                        child: Column(
                                          crossAxisAlignment:
                                              CrossAxisAlignment.start,
                                          children: [
                                            Text(
                                                '${AppStrings.t('date_time', isArabic: ar)} *',
                                                style: TextStyle(
                                                    fontSize: 12,
                                                    color: scheme
                                                        .onSurfaceVariant)),
                                            const SizedBox(height: 4),
                                            Text(
                                              '${DateFormatHelper.formatDate(_dateTime)} · ${DateFormat('h:mm a').format(_dateTime)}',
                                              style: TextStyle(
                                                  fontSize: 14,
                                                  fontWeight:
                                                      FontWeight.w500),
                                            ),
                                          ],
                                        ),
                                      ),
                                      Icon(Icons.edit_calendar,
                                          color: scheme.primary,
                                          size: 20),
                                    ],
                                  ),
                                ),
                              ),
                              const SizedBox(height: 24),

                              // ─────────────────────────────────────
                              // TREATMENT & PROCEDURE SECTION
                              // ─────────────────────────────────────
                              Text(AppStrings.t('treatment', isArabic: ar),
                                  style: Theme.of(context)
                                      .textTheme
                                      .labelLarge
                                      ?.copyWith(
                                          color: scheme.primary,
                                          fontWeight: FontWeight.w700)),
                              const SizedBox(height: 12),
                              DropdownButtonFormField<
                                  TreatmentProcedure>(
                                initialValue: _selectedTreatment,
                                decoration: InputDecoration(
                                  labelText:
                                      '${AppStrings.t('treatment_type', isArabic: ar)} *',
                                  hintText: _treatments.isEmpty
                                      ? AppStrings.t('no_treatments_available',
                                          isArabic: ar)
                                      : AppStrings.t('select_treatment',
                                          isArabic: ar),
                                  border: OutlineInputBorder(
                                      borderRadius:
                                          BorderRadius.circular(12)),
                                  contentPadding:
                                      const EdgeInsets.symmetric(
                                          horizontal: 16, vertical: 14),
                                ),
                                items: _treatments
                                    .map((t) => DropdownMenuItem(
                                          value: t,
                                          child: Text(t.name),
                                        ))
                                    .toList(),
                                onChanged: (t) => setState(
                                    () => _selectedTreatment = t),
                              ),
                              if (_selectedTreatment != null) ...[
                                const SizedBox(height: 12),
                                Container(
                                  padding: const EdgeInsets.all(12),
                                  decoration: BoxDecoration(
                                    color: scheme.primary.withAlpha(10),
                                    borderRadius:
                                        BorderRadius.circular(12),
                                    border: Border.all(
                                        color: scheme.primary
                                            .withAlpha(40)),
                                  ),
                                  child: Row(
                                    mainAxisAlignment:
                                        MainAxisAlignment.spaceBetween,
                                    children: [
                                      Text(
                                          AppStrings.t('default_price',
                                              isArabic: ar),
                                          style: TextStyle(
                                              fontSize: 12,
                                              color: scheme
                                                  .onSurfaceVariant)),
                                      Text(
                                        '₪${_selectedTreatment!.defaultPrice.toStringAsFixed(2)}',
                                        style: TextStyle(
                                            fontSize: 14,
                                            fontWeight: FontWeight.w700,
                                            color: scheme.primary),
                                      ),
                                    ],
                                  ),
                                ),
                              ],
                              const SizedBox(height: 14),
                              TextField(
                                controller: _durationCtrl,
                                decoration: InputDecoration(
                                  labelText:
                                      AppStrings.t('duration_minutes', isArabic: ar),
                                  border: OutlineInputBorder(
                                      borderRadius:
                                          BorderRadius.circular(12)),
                                  contentPadding:
                                      const EdgeInsets.symmetric(
                                          horizontal: 16, vertical: 14),
                                ),
                                keyboardType: TextInputType.number,
                              ),
                              const SizedBox(height: 24),

                              // ─────────────────────────────────────
                              // STATUS SECTION
                              // ─────────────────────────────────────
                              Text(AppStrings.t('status', isArabic: ar),
                                  style: Theme.of(context)
                                      .textTheme
                                      .labelLarge
                                      ?.copyWith(
                                          color: scheme.primary,
                                          fontWeight: FontWeight.w700)),
                              const SizedBox(height: 12),
                              DropdownButtonFormField<String>(
                                initialValue: _selectedStatus,
                                decoration: InputDecoration(
                                  border: OutlineInputBorder(
                                      borderRadius:
                                          BorderRadius.circular(12)),
                                  contentPadding:
                                      const EdgeInsets.symmetric(
                                          horizontal: 16, vertical: 14),
                                ),
                                items: const [
                                  'scheduled',
                                  'confirmed',
                                  'completed',
                                  'cancelled',
                                ]
                                    .map((status) =>
                                        DropdownMenuItem(
                                          value: status,
                                          child: Row(
                                            children: [
                                              Container(
                                                width: 8,
                                                height: 8,
                                                decoration:
                                                    BoxDecoration(
                                                  color: _statusColor(
                                                      status),
                                                  shape: BoxShape
                                                      .circle,
                                                ),
                                              ),
                                              const SizedBox(
                                                  width: 10),
                                              Text(AppStrings.t(
                                                  'status_$status',
                                                  isArabic: ar)),
                                            ],
                                          ),
                                        ))
                                    .toList(),
                                onChanged: (val) => setState(() =>
                                    _selectedStatus = val ?? 'scheduled'),
                              ),
                              const SizedBox(height: 24),

                              // ─────────────────────────────────────
                              // NOTES SECTION
                              // ─────────────────────────────────────
                              Text(AppStrings.t('notes', isArabic: ar),
                                  style: Theme.of(context)
                                      .textTheme
                                      .labelLarge
                                      ?.copyWith(
                                          color: scheme.primary,
                                          fontWeight: FontWeight.w700)),
                              const SizedBox(height: 12),
                              TextField(
                                controller: _notesCtrl,
                                decoration: InputDecoration(
                                  hintText: AppStrings.t(
                                      'additional_notes_optional',
                                      isArabic: ar),
                                  border: OutlineInputBorder(
                                      borderRadius:
                                          BorderRadius.circular(12)),
                                  contentPadding:
                                      const EdgeInsets.symmetric(
                                          horizontal: 16, vertical: 14),
                                ),
                                maxLines: 3,
                              ),
                              const SizedBox(height: 28),

                              // ─────────────────────────────────────
                              // ACTION BUTTONS
                              // ─────────────────────────────────────
                              Row(
                                children: [
                                  Expanded(
                                    child: OutlinedButton(
                                      onPressed: _saving
                                          ? null
                                          : () {
                                              _durationCtrl.text =
                                                  '30';
                                              _notesCtrl.clear();
                                              setState(() {
                                                _patient = null;
                                                _selectedTreatment =
                                                    null;
                                                _selectedStatus =
                                                    'scheduled';
                                                _dateTime = widget
                                                    .initialDate
                                                    .copyWith(
                                                        hour: 9,
                                                        minute: 0,
                                                        second: 0,
                                                        millisecond:
                                                            0);
                                              });
                                            },
                                      style: OutlinedButton.styleFrom(
                                        padding: const EdgeInsets
                                            .symmetric(
                                            horizontal: 16,
                                            vertical: 14),
                                        side: BorderSide(
                                            color: scheme.outline),
                                      ),
                                      child: Text(
                                          AppStrings.t('clear', isArabic: ar)),
                                    ),
                                  ),
                                  const SizedBox(width: 12),
                                  Expanded(
                                    child: GradientButton(
                                      label: AppStrings.t('schedule', isArabic: ar),
                                      loading: _saving,
                                      onPressed: _saving ||
                                              _patient == null ||
                                              _selectedTreatment == null
                                          ? null
                                          : _save,
                                      width: double.infinity,
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 20),
                            ],
                          ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

Color _statusColor(String status) {
  return switch (status) {
    'scheduled' => const Color(0xFFFFA500),
    'confirmed' => const Color(0xFF4CAF50),
    'completed' => const Color(0xFF2196F3),
    'cancelled' => const Color(0xFFE53935),
    _ => const Color(0xFF999999),
  };
}

extension on DateTime {
  DateTime copyWith(
          {int? year,
          int? month,
          int? day,
          int? hour,
          int? minute,
          int? second,
          int? millisecond}) =>
      DateTime(
        year ?? this.year,
        month ?? this.month,
        day ?? this.day,
        hour ?? this.hour,
        minute ?? this.minute,
        second ?? this.second,
        millisecond ?? this.millisecond,
      );
}
