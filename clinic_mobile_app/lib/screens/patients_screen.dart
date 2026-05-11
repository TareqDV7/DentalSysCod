import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../state/app_state.dart';
import '../models/patient.dart';
import '../widgets/empty_state.dart';
import '../utils/date_format_helper.dart';
import 'patient_detail_screen.dart';

class PatientsScreen extends StatefulWidget {
  const PatientsScreen({super.key});

  @override
  State<PatientsScreen> createState() => _PatientsScreenState();
}

class _PatientsScreenState extends State<PatientsScreen> {
  List<Patient> _patients = [];
  bool _loading = true;
  final _searchCtrl = TextEditingController();

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
    _load();
    _searchCtrl.addListener(() => _load(query: _searchCtrl.text));
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  Future<void> _load({String? query}) async {
    if (!mounted) return;
    setState(() => _loading = true);
    try {
      final state = context.read<AppState>();
      final list = await state.patients.getPatients(query: query);
      if (mounted) setState(() { _patients = list; _loading = false; });
    } catch (_) {
      if (mounted) setState(() => _loading = false);
      _showError('Unable to load patients right now');
    }
  }

  void _openAdd() {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _AddPatientSheet(
        onSaved: (p) async {
          await context.read<AppState>().patients.addPatient(p);
          if (mounted) _load();
        },
      ),
    );
  }

  Future<void> _deletePatient(Patient p) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Delete Patient'),
        content: Text('Delete ${p.fullName}? This cannot be undone.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Delete', style: TextStyle(color: Color(0xFFD9434E))),
          ),
        ],
      ),
    );
    if (ok == true && p.id != null && mounted) {
      await context.read<AppState>().patients.deletePatient(p.id!);
      _load();
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
            child: TextField(
              controller: _searchCtrl,
              decoration: const InputDecoration(
                hintText: 'Search by name, phone, or email…',
                prefixIcon: Icon(Icons.search),
              ),
            ),
          ),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _patients.isEmpty
                    ? EmptyState(
                        icon: Icons.people_outline,
                        message: 'No patients found',
                        actionLabel: 'Add Patient',
                        onAction: _openAdd,
                      )
                    : RefreshIndicator(
                        onRefresh: _load,
                        child: ListView.separated(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 16, vertical: 8),
                          itemCount: _patients.length,
                          separatorBuilder: (_, _) =>
                              const SizedBox(height: 8),
                          itemBuilder: (context, i) {
                            final p = _patients[i];
                            return Dismissible(
                              key: Key('patient_${p.id}'),
                              direction: DismissDirection.endToStart,
                              background: Container(
                                alignment: Alignment.centerRight,
                                padding: const EdgeInsets.only(right: 16),
                                decoration: BoxDecoration(
                                  color: const Color(0xFFD9434E),
                                  borderRadius: BorderRadius.circular(20),
                                ),
                                child: const Icon(Icons.delete,
                                    color: Colors.white),
                              ),
                              confirmDismiss: (_) async {
                                await _deletePatient(p);
                                return false;
                              },
                              child: _PatientTile(
                                patient: p,
                                onTap: () async {
                                  await Navigator.of(context, rootNavigator: true).push(
                                    MaterialPageRoute(
                                      builder: (_) => PatientDetailScreen(patient: p),
                                    ),
                                  );
                                  _load();
                                },
                              ),
                            );
                          },
                        ),
                      ),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _openAdd,
        backgroundColor: scheme.primary,
        foregroundColor: Colors.white,
        icon: const Icon(Icons.person_add),
        label: const Text('Add Patient',
            style: TextStyle(fontWeight: FontWeight.w700)),
      ),
    );
  }
}

class _PatientTile extends StatelessWidget {
  final Patient patient;
  final VoidCallback onTap;
  const _PatientTile({required this.patient, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final initials = '${patient.firstName[0]}${patient.lastName.isNotEmpty ? patient.lastName[0] : ''}'.toUpperCase();

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(20),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color: scheme.surface,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: scheme.outlineVariant),
        ),
        child: Row(
          children: [
            CircleAvatar(
              backgroundColor: const Color(0xFF0F6D7B).withAlpha(30),
              child: Text(initials,
                  style: const TextStyle(
                      color: Color(0xFF0F6D7B), fontWeight: FontWeight.w800)),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(patient.fullName,
                      style: const TextStyle(fontWeight: FontWeight.w700)),
                  if (patient.phone != null)
                    Text(patient.phone!,
                        style: TextStyle(
                            color: scheme.onSurfaceVariant, fontSize: 13)),
                ],
              ),
            ),
            Icon(Icons.chevron_right, color: scheme.onSurfaceVariant),
          ],
        ),
      ),
    );
  }
}

class _AddPatientSheet extends StatefulWidget {
  final Future<void> Function(Patient) onSaved;
  const _AddPatientSheet({required this.onSaved});

  @override
  State<_AddPatientSheet> createState() => _AddPatientSheetState();
}

class _AddPatientSheetState extends State<_AddPatientSheet> {
  final _form = GlobalKey<FormState>();
  final _first = TextEditingController();
  final _last = TextEditingController();
  final _phone = TextEditingController();
  final _email = TextEditingController();
  final _dob = TextEditingController();
  final _address = TextEditingController();
  final _history = TextEditingController();
  bool _saving = false;
  DateTime? _selectedDob;

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
  void dispose() {
    for (final c in [_first, _last, _phone, _email, _dob, _address, _history]) { c.dispose(); }
    super.dispose();
  }

  Future<void> _save() async {
    if (!_form.currentState!.validate()) return;
    setState(() => _saving = true);
    try {
      await widget.onSaved(Patient(
        firstName: _first.text.trim(),
        lastName: _last.text.trim(),
        phone: _phone.text.trim().isEmpty ? null : _phone.text.trim(),
        email: _email.text.trim().isEmpty ? null : _email.text.trim(),
        dateOfBirth: _selectedDob == null
            ? null
            : DateFormatHelper.formatDateForApi(_selectedDob!),
        address: _address.text.trim().isEmpty ? null : _address.text.trim(),
        medicalHistory: _history.text.trim().isEmpty ? null : _history.text.trim(),
      ));
      if (mounted) Navigator.pop(context);
    } catch (error) {
      _showError(error.toString());
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _pickDob() async {
    final initialDate = _selectedDob ?? DateTime(1990, 1, 1);
    final firstDate = DateTime(1900, 1, 1);
    final lastDate = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: initialDate.isAfter(lastDate) ? lastDate : initialDate,
      firstDate: firstDate,
      lastDate: lastDate,
      initialDatePickerMode: DatePickerMode.year,
    );
    if (picked == null || !mounted) return;
    setState(() {
      _selectedDob = picked;
      _dob.text = DateFormatHelper.formatDate(picked);
    });
  }

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      initialChildSize: 0.9,
      minChildSize: 0.5,
      maxChildSize: 0.95,
      builder: (_, scroll) => Container(
        decoration: BoxDecoration(
          color: Theme.of(context).scaffoldBackgroundColor,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
        ),
        child: SafeArea(
          top: false,
          child: Column(
            children: [
              const SizedBox(height: 8),
              Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                    color: Theme.of(context).colorScheme.outlineVariant,
                    borderRadius: BorderRadius.circular(2)),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
                child: Row(
                  children: [
                    Text('Add Patient',
                        style: Theme.of(context).textTheme.titleLarge),
                    const Spacer(),
                    IconButton(
                        onPressed: () => Navigator.pop(context),
                        icon: const Icon(Icons.close)),
                  ],
                ),
              ),
              Expanded(
                child: Form(
                  key: _form,
                  child: ListView(
                    controller: scroll,
                    padding: const EdgeInsets.all(16),
                    children: [
                    Row(children: [
                      Expanded(child: _field(_first, 'First Name', required: true)),
                      const SizedBox(width: 12),
                      Expanded(child: _field(_last, 'Last Name', required: true)),
                    ]),
                    const SizedBox(height: 12),
                    _field(_phone, 'Phone', type: TextInputType.phone),
                    const SizedBox(height: 12),
                    _field(_email, 'Email', type: TextInputType.emailAddress),
                    const SizedBox(height: 12),
                    TextFormField(
                      controller: _dob,
                      readOnly: true,
                      onTap: _pickDob,
                      decoration: const InputDecoration(
                        labelText: 'Date of Birth',
                        hintText: 'Tap to pick date',
                        suffixIcon: Icon(Icons.calendar_month_outlined),
                      ),
                      validator: (_) {
                        if (_dob.text.trim().isEmpty) return null;
                        return DateFormatHelper.parseDisplayDate(_dob.text.trim()) == null
                            ? 'Enter a valid date'
                            : null;
                      },
                    ),
                    const SizedBox(height: 12),
                    _field(_address, 'Address'),
                    const SizedBox(height: 12),
                    TextFormField(
                      controller: _history,
                      decoration: const InputDecoration(labelText: 'Medical History'),
                      maxLines: 3,
                    ),
                    const SizedBox(height: 20),
                    SizedBox(
                      width: double.infinity,
                      height: 48,
                      child: FilledButton(
                        onPressed: _saving ? null : _save,
                        child: _saving
                            ? const CircularProgressIndicator(color: Colors.white)
                            : const Text('Save Patient',
                                style: TextStyle(fontWeight: FontWeight.w800)),
                      ),
                    ),
                    const SizedBox(height: 16),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _field(TextEditingController c, String label,
      {bool required = false, TextInputType? type}) {
    return TextFormField(
      controller: c,
      keyboardType: type,
      decoration: InputDecoration(labelText: label),
      validator: required
          ? (v) => (v == null || v.trim().isEmpty) ? 'Required' : null
          : null,
    );
  }
}
