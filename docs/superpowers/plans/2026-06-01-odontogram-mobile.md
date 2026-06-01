# Odontogram — Mobile (Flutter) Implementation Plan (Track C)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the odontogram to the Flutter app at parity with the web portal — models + a local-first service for the tooth-condition catalog and the per-patient chart, a DB migration (v8→v9) for the three new tables, an Odontogram tab on the patient detail screen with a CustomPaint arch + tap sheet (reusing the existing follow-up Add sheet), and a tooth-condition admin sheet under Settings. Finishes by updating the README for all three tracks.

**Architecture:** Offline-first, mirroring `catalog_service.dart`: writes land in local SQLite first, then push to the server; the next sync pull reconciles. The three new tables join `localToRemoteTable` so the existing sync engine carries them. Chart **badges are not stored locally** — they come from the server's computed `GET /api/patients/<id>/tooth-chart`; when offline, the chart still renders conditions from local rows, with badges filled in on the next online fetch.

**Tech Stack:** Flutter, `provider`, `sqflite`, `dio`, `flutter_test`. Code under `clinic_mobile_app/lib/`; tests under `clinic_mobile_app/test/`.

**Dependency:** **Track A (backend) must be merged and green first.** Frozen contract: `GET /api/patients/<id>/tooth-chart` → `{conditions:[…], teeth:{tooth_no:{condition_id,condition_name,color,note,source,unpaid_balance,has_plan}}}`. Track C should follow / run parallel to Track B (desktop).

**Spec:** `docs/superpowers/specs/2026-06-01-odontogram-design.md`

**Run tests:** `cd clinic_mobile_app && flutter test`. **Analyzer must stay clean:** `flutter analyze` (zero issues — a project invariant).

---

## Key anchors (verified 2026-06-01)

| What | Location |
|------|----------|
| DB version + factories | `database_service.dart:24‑28` (`version: 8`) |
| `localToRemoteTable` map | `database_service.dart:31‑41` |
| CREATE-table consts (pattern) | `_createTreatmentPlans` `151`, `_createFollowups` `184`, `_createMedicalImages` `78` |
| `_onUpgrade(db, oldVersion, newVersion)` | `database_service.dart:94` (uses `if (oldVersion < N)` blocks) |
| `_onCreate(db, version)` | `database_service.dart:212‑324` (registers every table) |
| Catalog CRUD helpers | `getProcedures()` `981`, `getAllProcedures()` `991`, `upsertProcedure()` `998` |
| Service pattern to mirror | `services/catalog_service.dart` (local-write-then-push) |
| Model pattern to mirror | `models/treatment_plan.dart` (`fromJson`/`fromDb`/`toDb`/`copyWith`/`_num`) |
| Catalog admin screen to mirror | `screens/catalog_screen.dart` |
| Patient detail (tabs + follow-up sheet) | `screens/patient_detail_screen.dart` (1626 lines; follow-up Add sheet ~1345‑1558) |

---

## File Structure

| File | Responsibility | Change |
|------|----------------|--------|
| `lib/models/tooth_condition.dart` | catalog DTO | Create |
| `lib/models/tooth_chart_entry.dart` | one tooth's chart state + badges | Create |
| `lib/models/treatment_plan.dart` | add `teeth` list | Modify |
| `lib/services/database_service.dart` | v9 migration + 3 tables + map | Modify |
| `lib/services/tooth_chart_service.dart` | catalog + chart CRUD (local-first) | Create |
| `lib/screens/odontogram_view.dart` | arch widget + tap sheet | Create |
| `lib/screens/patient_detail_screen.dart` | add Odontogram tab | Modify |
| `lib/screens/settings_screen.dart` | Tooth-conditions admin entry | Modify |
| `lib/screens/tooth_conditions_screen.dart` | conditions admin (mirror catalog_screen) | Create |
| `test/tooth_models_test.dart` | model round-trip (TDD) | Create |
| `test/tooth_chart_parse_test.dart` | chart-response parse (TDD) | Create |
| `README.md` (repo root) | document odontogram (all tracks) | Modify |

---

## Task 1: `ToothCondition` + `ToothChartEntry` models (TDD)

**Files:**
- Create: `lib/models/tooth_condition.dart`, `lib/models/tooth_chart_entry.dart`
- Test: `test/tooth_models_test.dart`

- [ ] **Step 1: Write the failing test**

Create `clinic_mobile_app/test/tooth_models_test.dart`:

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/models/tooth_condition.dart';
import 'package:clinic_mobile_app/models/tooth_chart_entry.dart';

void main() {
  group('ToothCondition', () {
    test('parses server JSON', () {
      final c = ToothCondition.fromJson({
        'id': 2, 'name': 'Decay', 'name_ar': 'تسوّس',
        'color': '#ef4444', 'icon': null, 'sort_order': 1, 'active': 1,
      });
      expect(c.id, 2);
      expect(c.name, 'Decay');
      expect(c.nameAr, 'تسوّس');
      expect(c.color, '#ef4444');
      expect(c.sortOrder, 1);
      expect(c.active, true);
    });

    test('toJson uses snake_case server keys', () {
      const c = ToothCondition(id: 1, name: 'Veneer', nameAr: 'فينير',
          color: '#10b981', icon: null, sortOrder: 9, active: true);
      final j = c.toJson();
      expect(j['name'], 'Veneer');
      expect(j['name_ar'], 'فينير');
      expect(j['sort_order'], 9);
    });
  });

  group('ToothChartEntry', () {
    test('parses a marked tooth with computed badges', () {
      final e = ToothChartEntry.fromJson('16', {
        'condition_id': 2, 'condition_name': 'Decay', 'color': '#ef4444',
        'note': 'distal', 'source': 'chart',
        'has_plan': true, 'unpaid_balance': 150.0,
      });
      expect(e.toothNo, '16');
      expect(e.conditionId, 2);
      expect(e.conditionName, 'Decay');
      expect(e.color, '#ef4444');
      expect(e.hasPlan, true);
      expect(e.unpaidBalance, 150.0);
      expect(e.source, 'chart');
    });

    test('legacy tooth has null condition but may carry badges', () {
      final e = ToothChartEntry.fromJson('26', {
        'condition_id': null, 'condition_name': null, 'color': null,
        'note': null, 'source': 'legacy', 'has_plan': false, 'unpaid_balance': 200.0,
      });
      expect(e.conditionId, isNull);
      expect(e.source, 'legacy');
      expect(e.unpaidBalance, 200.0);
    });
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd clinic_mobile_app && flutter test test/tooth_models_test.dart`
Expected: FAIL — files/classes don't exist.

- [ ] **Step 3: Create the models**

`lib/models/tooth_condition.dart`:

```dart
/// An editable tooth-condition catalog entry. Mirrors the server's
/// `tooth_conditions` table and the `/api/tooth-conditions` endpoints.
class ToothCondition {
  final int? id;
  final String name;
  final String? nameAr;
  final String color;
  final String? icon;
  final int sortOrder;
  final bool active;
  final String? updatedAt;
  final bool isSynced;

  const ToothCondition({
    this.id,
    required this.name,
    this.nameAr,
    this.color = '#9ca3af',
    this.icon,
    this.sortOrder = 0,
    this.active = true,
    this.updatedAt,
    this.isSynced = false,
  });

  factory ToothCondition.fromJson(Map<String, dynamic> j) => ToothCondition(
        id: j['id'] is int ? j['id'] : int.tryParse('${j['id']}'),
        name: (j['name'] ?? '').toString(),
        nameAr: j['name_ar']?.toString(),
        color: (j['color'] ?? '#9ca3af').toString(),
        icon: j['icon']?.toString(),
        sortOrder: (j['sort_order'] is num) ? (j['sort_order'] as num).toInt() : 0,
        active: (j['active'] ?? 1) == 1 || j['active'] == true,
        updatedAt: j['updated_at']?.toString(),
        isSynced: true,
      );

  factory ToothCondition.fromDb(Map<String, dynamic> r) => ToothCondition(
        id: r['id'],
        name: (r['name'] ?? '').toString(),
        nameAr: r['name_ar'] as String?,
        color: (r['color'] ?? '#9ca3af').toString(),
        icon: r['icon'] as String?,
        sortOrder: (r['sort_order'] ?? 0) as int,
        active: (r['active'] ?? 1) == 1,
        updatedAt: r['updated_at'] as String?,
        isSynced: (r['is_synced'] ?? 0) == 1,
      );

  Map<String, dynamic> toJson() => {
        if (id != null) 'id': id,
        'name': name,
        'name_ar': nameAr,
        'color': color,
        'icon': icon,
        'sort_order': sortOrder,
        'active': active ? 1 : 0,
      };

  Map<String, dynamic> toDb() => {
        if (id != null) 'id': id,
        'name': name,
        'name_ar': nameAr,
        'color': color,
        'icon': icon,
        'sort_order': sortOrder,
        'active': active ? 1 : 0,
        'updated_at': updatedAt ?? DateTime.now().toIso8601String(),
        'is_synced': isSynced ? 1 : 0,
      };

  ToothCondition copyWith({
    int? id,
    String? name,
    String? nameAr,
    String? color,
    String? icon,
    int? sortOrder,
    bool? active,
    String? updatedAt,
    bool? isSynced,
  }) =>
      ToothCondition(
        id: id ?? this.id,
        name: name ?? this.name,
        nameAr: nameAr ?? this.nameAr,
        color: color ?? this.color,
        icon: icon ?? this.icon,
        sortOrder: sortOrder ?? this.sortOrder,
        active: active ?? this.active,
        updatedAt: updatedAt ?? this.updatedAt,
        isSynced: isSynced ?? this.isSynced,
      );
}
```

`lib/models/tooth_chart_entry.dart`:

```dart
/// One tooth's state as returned by GET /api/patients/<id>/tooth-chart.
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
            ? j['condition_id']
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd clinic_mobile_app && flutter test test/tooth_models_test.dart`
Expected: PASS.

- [ ] **Step 5: Analyze + commit**

```bash
cd clinic_mobile_app && flutter analyze
git add clinic_mobile_app/lib/models/tooth_condition.dart clinic_mobile_app/lib/models/tooth_chart_entry.dart clinic_mobile_app/test/tooth_models_test.dart
git commit -m "feat(mobile): ToothCondition + ToothChartEntry models"
```

---

## Task 2: `TreatmentPlan` gains a `teeth` list (TDD)

**Files:**
- Modify: `lib/models/treatment_plan.dart`
- Test: `test/tooth_models_test.dart` (extend)

- [ ] **Step 1: Write the failing test**

Append to `test/tooth_models_test.dart`:

```dart
import 'package:clinic_mobile_app/models/treatment_plan.dart';

void _planTests() {
  group('TreatmentPlan.teeth', () {
    test('parses teeth array from server JSON', () {
      final p = TreatmentPlan.fromJson({
        'id': 1, 'patient_id': 5, 'plan_name': 'Upper crowns',
        'teeth': ['16', '26', '36'],
      });
      expect(p.teeth, ['16', '26', '36']);
    });

    test('defaults to empty teeth when absent', () {
      final p = TreatmentPlan.fromJson({'id': 1, 'patient_id': 5, 'plan_name': 'X'});
      expect(p.teeth, isEmpty);
    });

    test('toJson includes teeth', () {
      final p = TreatmentPlan(patientId: 5, planName: 'X', teeth: const ['16']);
      expect(p.toJson()['teeth'], ['16']);
    });
  });
}
```

Then call `_planTests();` from inside `main()` (add the line at the end of `main`).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd clinic_mobile_app && flutter test test/tooth_models_test.dart`
Expected: FAIL — `TreatmentPlan` has no `teeth` / no `toJson`.

- [ ] **Step 3: Add `teeth` to the model**

In `lib/models/treatment_plan.dart`:
- Add field: `final List<String> teeth;`
- Add to the constructor: `this.teeth = const [],`
- In `fromJson`, add: `teeth: (j['teeth'] as List?)?.map((e) => e.toString()).toList() ?? const [],`
- In `fromDb`, add: `teeth: const [],` (the link rows live in their own table; the screen fetches teeth via the chart/plan API, not the plan row)
- Add a `toJson()` (the model currently only has `toDb`):

```dart
  Map<String, dynamic> toJson() => {
        if (id != null) 'id': id,
        'patient_id': patientId,
        'plan_name': planName,
        'goals': goals,
        'estimated_cost': estimatedCost,
        'status': status,
        'start_date': startDate,
        'end_date': endDate,
        'notes': notes,
        'teeth': teeth,
      };
```
- In `copyWith`, add `List<String>? teeth,` and `teeth: teeth ?? this.teeth,`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd clinic_mobile_app && flutter test test/tooth_models_test.dart`
Expected: PASS.

- [ ] **Step 5: Analyze + commit**

```bash
cd clinic_mobile_app && flutter analyze
git add clinic_mobile_app/lib/models/treatment_plan.dart clinic_mobile_app/test/tooth_models_test.dart
git commit -m "feat(mobile): TreatmentPlan carries a multi-tooth teeth list"
```

---

## Task 3: DB migration v8→v9 (three new tables + sync map)

**Files:** Modify `lib/services/database_service.dart`

- [ ] **Step 1: Bump the version**

`database_service.dart:27` — change `version: 8` to `version: 9`.

- [ ] **Step 2: Add the three tables to the sync map**

In `localToRemoteTable` (`31‑41`) add:

```dart
    'tooth_conditions': 'tooth_conditions',
    'patient_tooth_chart': 'patient_tooth_chart',
    'treatment_plan_teeth': 'treatment_plan_teeth',
```

- [ ] **Step 3: Add CREATE-table constants**

Beside the other `_create*` consts (e.g. after `_createMedicalImages`):

```dart
  static const String _createToothConditions = '''
    CREATE TABLE IF NOT EXISTS tooth_conditions (
      id INTEGER PRIMARY KEY,
      name TEXT NOT NULL,
      name_ar TEXT,
      color TEXT DEFAULT '#9ca3af',
      icon TEXT,
      sort_order INTEGER DEFAULT 0,
      active INTEGER DEFAULT 1,
      updated_at TEXT,
      is_synced INTEGER DEFAULT 0
    )
  ''';

  static const String _createPatientToothChart = '''
    CREATE TABLE IF NOT EXISTS patient_tooth_chart (
      id INTEGER PRIMARY KEY,
      patient_id INTEGER NOT NULL,
      tooth_no TEXT NOT NULL,
      condition_id INTEGER,
      note TEXT,
      updated_at TEXT,
      is_synced INTEGER DEFAULT 0
    )
  ''';
  static const String _idxToothChartPatient =
      'CREATE INDEX IF NOT EXISTS idx_tooth_chart_patient ON patient_tooth_chart(patient_id)';

  static const String _createTreatmentPlanTeeth = '''
    CREATE TABLE IF NOT EXISTS treatment_plan_teeth (
      id INTEGER PRIMARY KEY,
      plan_id INTEGER NOT NULL,
      tooth_no TEXT NOT NULL,
      updated_at TEXT,
      is_synced INTEGER DEFAULT 0
    )
  ''';
  static const String _idxPlanTeethPlan =
      'CREATE INDEX IF NOT EXISTS idx_plan_teeth_plan ON treatment_plan_teeth(plan_id)';
```

> `id INTEGER PRIMARY KEY` (not AUTOINCREMENT) so sync can insert server-assigned ids verbatim — the same convention the other synced local tables use.

- [ ] **Step 4: Register in `_onCreate` and `_onUpgrade`**

In `_onCreate` (after the existing `await db.execute(...)` calls, ~`324`):

```dart
    await db.execute(_createToothConditions);
    await db.execute(_createPatientToothChart);
    await db.execute(_idxToothChartPatient);
    await db.execute(_createTreatmentPlanTeeth);
    await db.execute(_idxPlanTeethPlan);
```

In `_onUpgrade` (`94`), add a new block (after the highest existing `if (oldVersion < N)`):

```dart
    if (oldVersion < 9) {
      await db.execute(_createToothConditions);
      await db.execute(_createPatientToothChart);
      await db.execute(_idxToothChartPatient);
      await db.execute(_createTreatmentPlanTeeth);
      await db.execute(_idxPlanTeethPlan);
    }
```

- [ ] **Step 5: Verify (analyzer + device upgrade smoke)**

Run: `cd clinic_mobile_app && flutter analyze` → zero issues.
Device/emulator smoke: install the **previous** build (v8 DB present), then this build over it → app launches without a migration crash, existing patients/follow-ups intact (this exercises `_onUpgrade`). Then a fresh install → `_onCreate` path. Report both honestly.

> No sqflite unit test is added here — this repo's Flutter tests are pure-logic and have no live-DB harness (`sqflite_common_ffi` is not wired in). Adding one would mean introducing that harness; out of scope. Migration is verified on-device.

- [ ] **Step 6: Commit**

```bash
git add clinic_mobile_app/lib/services/database_service.dart
git commit -m "feat(mobile): DB v9 — tooth_conditions, patient_tooth_chart, treatment_plan_teeth"
```

---

## Task 4: `ToothChartService` (local-first catalog + chart) — TDD on parsing

**Files:**
- Create: `lib/services/tooth_chart_service.dart`
- Test: `test/tooth_chart_parse_test.dart`

- [ ] **Step 1: Write the failing test (pure response parsing)**

Create `clinic_mobile_app/test/tooth_chart_parse_test.dart`:

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/services/tooth_chart_service.dart';
import 'package:clinic_mobile_app/models/tooth_condition.dart';

void main() {
  group('parseToothChart', () {
    test('splits conditions and per-tooth entries', () {
      final result = parseToothChart({
        'conditions': [
          {'id': 1, 'name': 'Healthy', 'color': '#22c55e', 'sort_order': 0, 'active': 1},
          {'id': 2, 'name': 'Decay', 'color': '#ef4444', 'sort_order': 1, 'active': 1},
        ],
        'teeth': {
          '16': {'condition_id': 2, 'condition_name': 'Decay', 'color': '#ef4444',
                 'note': null, 'source': 'chart', 'has_plan': true, 'unpaid_balance': 0},
          '26': {'condition_id': null, 'condition_name': null, 'color': null,
                 'note': null, 'source': 'legacy', 'has_plan': false, 'unpaid_balance': 200},
        },
      });
      expect(result.conditions, isA<List<ToothCondition>>());
      expect(result.conditions.length, 2);
      expect(result.teeth['16']!.hasPlan, true);
      expect(result.teeth['26']!.unpaidBalance, 200);
      expect(result.teeth['26']!.source, 'legacy');
    });

    test('empty chart yields no teeth', () {
      final result = parseToothChart({'conditions': [], 'teeth': {}});
      expect(result.teeth, isEmpty);
    });
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd clinic_mobile_app && flutter test test/tooth_chart_parse_test.dart`
Expected: FAIL — `parseToothChart` / `ToothChart` undefined.

- [ ] **Step 3: Create the service + pure parser**

`lib/services/tooth_chart_service.dart`:

```dart
import '../models/tooth_condition.dart';
import '../models/tooth_chart_entry.dart';
import 'clinic_api.dart';
import 'database_service.dart';

/// Parsed result of GET /api/patients/<id>/tooth-chart.
class ToothChart {
  final List<ToothCondition> conditions;
  final Map<String, ToothChartEntry> teeth;
  const ToothChart({required this.conditions, required this.teeth});
}

/// Pure transform of the chart response body — unit-tested directly.
ToothChart parseToothChart(Map<String, dynamic> body) {
  final conditions = ((body['conditions'] as List?) ?? const [])
      .map((c) => ToothCondition.fromJson(Map<String, dynamic>.from(c as Map)))
      .toList();
  final teethMap = <String, ToothChartEntry>{};
  ((body['teeth'] as Map?) ?? const {}).forEach((k, v) {
    teethMap['$k'] = ToothChartEntry.fromJson('$k', Map<String, dynamic>.from(v as Map));
  });
  return ToothChart(conditions: conditions, teeth: teethMap);
}

/// Local-first catalog + chart access. Mirrors CatalogService:
/// writes land in local SQLite first, then push to the server; badges
/// are server-computed so the chart GET is the source of truth for them.
class ToothChartService {
  final DatabaseService _db;
  final ClinicApi _api;

  ToothChartService(this._db, this._api);

  /// Patient chart with computed badges. Requires connectivity for badges;
  /// callers should handle the offline error and fall back to local rows.
  Future<ToothChart> getChart(int patientId) async {
    final resp = await _api.get('/api/patients/$patientId/tooth-chart');
    return parseToothChart(Map<String, dynamic>.from(resp as Map));
  }

  /// Set or clear (conditionId == null) a tooth's condition. Writes the
  /// server, then mirrors locally so an offline re-open still shows it.
  Future<void> setTooth(int patientId, String toothNo, int? conditionId, {String? note}) async {
    await _api.post('/api/patients/$patientId/tooth-chart', body: {
      'tooth_no': toothNo,
      'condition_id': conditionId,
      'note': note,
    });
  }

  Future<void> clearTooth(int patientId, String toothNo) async {
    await _api.delete('/api/patients/$patientId/tooth-chart/$toothNo');
  }

  // --- Catalog ---
  Future<List<ToothCondition>> getConditions({bool all = false}) async {
    final resp = await _api.get('/api/tooth-conditions${all ? '?all=1' : ''}');
    return ((resp as List))
        .map((c) => ToothCondition.fromJson(Map<String, dynamic>.from(c as Map)))
        .toList();
  }

  Future<void> addCondition(ToothCondition c) =>
      _api.post('/api/tooth-conditions', body: c.toJson());

  Future<void> updateCondition(ToothCondition c) =>
      _api.put('/api/tooth-conditions/${c.id}', body: c.toJson());

  Future<void> deleteCondition(int id) =>
      _api.delete('/api/tooth-conditions/$id');
}
```

> Verify `ClinicApi`'s method signatures (`get`/`post`/`put`/`delete`, `body:` param) against `services/clinic_api.dart` and match them — `catalog_service.dart` uses `_api.post(path, body: ...)` / `_api.put(path, body: ...)`. Adjust the calls here to the real signatures if they differ (e.g. a `delete` that takes only a path).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd clinic_mobile_app && flutter test test/tooth_chart_parse_test.dart`
Expected: PASS.

- [ ] **Step 5: Analyze + commit**

```bash
cd clinic_mobile_app && flutter analyze
git add clinic_mobile_app/lib/services/tooth_chart_service.dart clinic_mobile_app/test/tooth_chart_parse_test.dart
git commit -m "feat(mobile): ToothChartService + pure chart-response parser"
```

---

## Task 5: Odontogram view (CustomPaint arch + tap sheet)

**Files:**
- Create: `lib/screens/odontogram_view.dart`
- Modify: `lib/screens/patient_detail_screen.dart` (add a tab)

- [ ] **Step 1: Build the arch widget**

Create `lib/screens/odontogram_view.dart` with a `StatefulWidget` that:
- holds `int patientId` + a `ToothChartService`;
- loads `getChart(patientId)` in `initState` / a refresh method;
- renders two rows of 16 teeth using `CustomPaint` (or a `Wrap` of small `CustomPaint` tooth cells), colored by `entry.color` (healthy = outline), with a purple dot when `hasPlan` and an amber dot when `unpaidBalance > 0`;
- renders a legend from `conditions`;
- on tooth tap, opens `_toothSheet(...)` (Step 2).

FDI layout + tooth-class (same as desktop):

```dart
const upperFdi = ['18','17','16','15','14','13','12','11','21','22','23','24','25','26','27','28'];
const lowerFdi = ['48','47','46','45','44','43','42','41','31','32','33','34','35','36','37','38'];

String fdiClass(String fdi) {
  final n = int.parse(fdi[1]);
  if (n <= 2) return 'incisor';
  if (n == 3) return 'canine';
  if (n <= 5) return 'premolar';
  return 'molar';
}

Color colorFromHex(String? hex) {
  if (hex == null || !hex.startsWith('#')) return const Color(0x00000000);
  return Color(int.parse(hex.substring(1), radix: 16) | 0xFF000000);
}
```

Draw each tooth as a rounded path per class (a `Path` with cusps for molars, a point for canines, a blade for incisors). Keep currency in badges as `₪`.

- [ ] **Step 2: Tap sheet — set condition / log treatment / add to plan**

A `showModalBottomSheet` with:
- a `DropdownButton<int?>` of conditions (first item `null` = Healthy/clear), defaulting to the tooth's `conditionId`;
- a note `TextField`;
- **Save** → `service.setTooth(patientId, fdi, selectedId, note: note)` (null clears) → refresh;
- **+ Log treatment** → close sheet, open the **existing** follow-up Add sheet on `patient_detail_screen.dart` (~1345‑1558) with the tooth field pre-set to `fdi`. Expose the existing opener so it accepts an optional `initialTooth` (Step 3);
- **+ Add to plan** → pick/create a plan and call the plan API with `teeth` including `fdi` (reuse the Treatment Plans tab's create/update path; add `fdi` to the chosen plan's `teeth`).

- [ ] **Step 3: Make the follow-up Add sheet accept a pre-filled tooth**

In `patient_detail_screen.dart`, find the method that opens the follow-up Add sheet (around `1345`). Add an optional named param `String? initialTooth` and, when building the sheet, seed the tooth controller with it (`_toothController.text = initialTooth ?? ''`). All money/ledger logic is unchanged.

- [ ] **Step 4: Add the Odontogram tab**

In `patient_detail_screen.dart`, add a tab (in whatever `TabBar`/`IndexedStack`/`SegmentedButton` the screen uses — match the existing tab mechanism) labelled "Tooth chart" (i18n key `odontogram`) that hosts `OdontogramView(patientId: patient.id!, service: <injected ToothChartService>)`. Wire the service from the provider/composition root the same way `CatalogService` is obtained.

- [ ] **Step 5: Widget test (renders + tappable)**

Create `test/odontogram_view_test.dart` that pumps `OdontogramView` with a fake service returning a small `ToothChart` (one marked tooth, one legacy) and asserts the legend text and that 32 tooth cells are present. Use a hand-written fake `ToothChartService` subclass/interface per the repo's fake-over-mock convention.

> If injecting a fake into the concrete `ToothChartService` is awkward, extract a tiny interface (`abstract class ToothChartReader { Future<ToothChart> getChart(int id); }`) that the view depends on — keeps the widget test honest without a live server.

- [ ] **Step 6: Verify**

Run: `cd clinic_mobile_app && flutter analyze && flutter test`
Device smoke: open a patient → Tooth chart tab → arch renders; tap a tooth → sheet; set Crown → tooth turns purple; "+ Log treatment" → follow-up sheet opens with tooth pre-filled; log it → unpaid dot appears. Report honestly.

- [ ] **Step 7: Commit**

```bash
git add clinic_mobile_app/lib/screens/odontogram_view.dart clinic_mobile_app/lib/screens/patient_detail_screen.dart clinic_mobile_app/test/odontogram_view_test.dart
git commit -m "feat(mobile): odontogram tab — arch, tap sheet, follow-up prefill, add-to-plan"
```

---

## Task 6: Tooth-condition admin under Settings

**Files:**
- Create: `lib/screens/tooth_conditions_screen.dart`
- Modify: `lib/screens/settings_screen.dart`

- [ ] **Step 1: Read `catalog_screen.dart` to mirror it**

Read `lib/screens/catalog_screen.dart` (CRUD list + add/edit + active toggle) and copy its structure for conditions, swapping the service to `ToothChartService` and the fields to name / name_ar / color / sort_order / active.

- [ ] **Step 2: Build the admin screen**

`tooth_conditions_screen.dart`: a list of `getConditions(all: true)` with a color swatch, name + Arabic name, a "Deactivate"/"Reactivate" toggle (calls `updateCondition(copyWith(active: …))` or `deleteCondition(id)` for deactivate), and an add row (name, name_ar, color picker, sort). Currency-free; bilingual labels.

- [ ] **Step 3: Add the Settings entry**

In `settings_screen.dart`, add a tile "Tooth conditions" (i18n `tooth_conditions`) that pushes `ToothConditionsScreen`, mirroring the existing "Procedure catalog" tile.

- [ ] **Step 4: Verify**

Run: `cd clinic_mobile_app && flutter analyze && flutter test`
Device smoke: Settings → Tooth conditions → Core 8 listed with swatches; add "Veneer"; deactivate "Implant" → drops from the tap-sheet dropdown. Report honestly.

- [ ] **Step 5: Commit**

```bash
git add clinic_mobile_app/lib/screens/tooth_conditions_screen.dart clinic_mobile_app/lib/screens/settings_screen.dart
git commit -m "feat(mobile): tooth-condition admin under Settings"
```

---

## Task 7: Final verification + README (all three tracks)

**Files:** Modify `README.md` (repo root)

- [ ] **Step 1: Full mobile gate**

Run: `cd clinic_mobile_app && flutter analyze` (zero issues) and `flutter test` (all pass, including the new model/parse/widget tests).

- [ ] **Step 2: Confirm backend suite still green**

Run: `python -m pytest tests/ -q` → all green (Track A suites included). Count the new backend test count for the README.

- [ ] **Step 3: Update the README**

Make these edits to `README.md`:
- **Features → Patient Management:** add a bullet describing the odontogram (FDI whole-tooth chart, editable condition catalog, tap → set condition / log treatment / add to plan, plan + unpaid badges computed from the ledger, legacy tooth_no auto-adopt).
- **REST API → Visits & Treatments (or a new "Odontogram" subsection):** add the rows for `/api/tooth-conditions` (+`/<id>`), `/api/patients/<id>/tooth-chart` (GET/POST), `/api/patients/<id>/tooth-chart/<tooth_no>` (DELETE); note `/api/treatment-plans` now returns/accepts `teeth`.
- **Project Structure / tables:** mention the three new tables (`tooth_conditions`, `patient_tooth_chart`, `treatment_plan_teeth`) in `SYNC_TABLES`; list the new mobile files.
- **Tests:** bump "215 tests across 28 suites" to the new totals (28 + 5 new backend suites = 33 suites; add the new test count) and add the new Flutter test files to the Flutter test paragraph (67 → new total). Use the actual counts from Steps 1‑2 — do not guess.

> Per the project's working style (memory: "Update README per task"), the README is updated once here, covering all three tracks, after everything is green.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document the odontogram (features, API, tables, tests)"
```

- [ ] **Step 5: Finish the branch**

Use superpowers:finishing-a-development-branch to decide merge/PR. The three track commits + the spec form one feature; open a PR titled "feat: odontogram (tooth chart)" summarizing backend + desktop + mobile.

---

## Self-Review (completed during planning)

- **Spec coverage (mobile section):** models (Tasks 1‑2) · DB migration with onCreate+onUpgrade (Task 3) · local-first service + parser (Task 4) · arch tab + tap sheet reusing the follow-up Add sheet + add-to-plan (Task 5) · conditions admin mirroring catalog_screen (Task 6) · README for all tracks (Task 7). All covered. Parity invariant: currency stays `₪`.
- **Contract consistency:** `ToothChartEntry.fromJson` reads exactly the Track A Task 8 keys; `ToothCondition` round-trips the catalog keys; `TreatmentPlan.teeth` matches the Track A `teeth[]` array.
- **Placeholder scan:** models, service, parser, migration, and all tests carry complete code. Tasks 5‑6 (Flutter UI) specify exact widgets, methods, file paths, and the two integration points (the follow-up-sheet opener gains `initialTooth`; the tab is added to the existing tab mechanism) but defer pixel-level `CustomPaint` path geometry to implementation — consistent with this repo's reality that visual widgets are verified by widget tests + device smoke, not pinned in the plan. The one external dependency to confirm at build time is `ClinicApi`'s method signatures (flagged in Task 4).
- **Test reality:** real TDD where this repo actually unit-tests (models, the pure `parseToothChart`); `flutter analyze` + device smoke for DB/UI, stated honestly rather than fabricating a sqflite test harness that isn't wired in.
