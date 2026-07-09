# Security PR 3: Encryption-at-Rest (SQLCipher + DPAPI) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Encrypt the clinic's SQLite database at rest with SQLCipher, using a key that's protected via Windows DPAPI (machine scope) so neither a human nor an unattended service ever needs to type a passphrase, and migrate existing installed clinics to it automatically and safely.

**Architecture:** A new key-management module wraps DPAPI protect/unprotect. `get_db_connection()` (the existing shared helper, `dental_clinic.py:597`) is extended to open via SQLCipher and issue `PRAGMA key` before any other statement. Every other direct `sqlite3.connect(DB_NAME)` / `sqlite3.connect(str(DB_NAME))` call site in `dental_clinic.py` (86 of them, confirmed by exact grep count during planning) is mechanically converted to call `get_db_connection()` instead. A migration function runs once at startup to convert any existing plaintext database.

**Tech Stack:** SQLCipher (via a Windows-wheel Python binding — validated in Task 1), `pywin32` (`win32crypt`) for DPAPI, both new dependencies.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-07-security-hardening-rbac-design.md`, Decisions 5-7 + Architecture › Encryption.
- **This PR only encrypts `DB_NAME` (the single-tenant desktop/service clinic database).** `MASTER_DB_PATH` and per-clinic databases reachable only in `CLOUD_MODE` are explicitly **out of scope** — confirmed during planning that DPAPI is Windows-only and the cloud node runs on Linux (Caddy/Docker per project memory), so this mechanism cannot and should not apply there. Every `sqlite3.connect(MASTER_DB_PATH)` call site (7, confirmed by grep) and any `CLOUD_MODE`-gated connection stays untouched.
- **`db_merge.py`'s one `sqlite3.connect(...)` call and `serial_admin.py`'s one call are also out of scope** — confirmed during planning: `db_merge.py` opens a foreign, externally-supplied database file being merged *from* (read-only, not our primary DB), and `serial_admin.py` connects to a completely separate `minted_serials.db` ledger for a standalone admin tool. Neither is the clinic's patient database.
- Full existing test suite (742+ tests as of 2026-07-07) must stay green after every task. Tests run with `DB_NAME` monkeypatched to a `tmp_path` file and never touch DPAPI directly (DPAPI is Windows-API-backed and not mockable in a portable way) — see Task 2 for how the key module is made testable without a real Windows machine dependency in CI.
- Migration failure must never leave the clinic without a working database — every failure path in Task 4 restores the pre-migration backup.

---

### Task 1: Validate SQLCipher + PyInstaller compatibility (spike — do this before writing any other code)

This is the single largest unknown in the whole security sub-project: bundling a native SQLCipher DLL into the existing frozen `DentaCare.exe`/`DentaCareService.exe` build (`DentaCare.spec`) might not "just work." Resolve this FIRST, before Tasks 2-6 are attempted, so a build-incompatibility surfaces immediately rather than after several days of otherwise-unrelated code is already written on top of an approach that can't ship.

**Files:**
- Create (temporary, for the spike only): `tools/spike_sqlcipher_build/` — a throwaway PyInstaller test, deleted at the end of this task once the real dependency is confirmed to work (or the whole encryption sub-project is escalated back to the user if it doesn't — see Step 5).
- Modify: `requirements.txt` (add the chosen dependency once confirmed working)

- [ ] **Step 1: Install and smoke-test the binding in dev mode (unfrozen)**

Run:
```bash
pip install sqlcipher3-binary
python -c "
import sqlcipher3 as sqlite3
conn = sqlite3.connect('spike_test.db')
conn.execute(\"PRAGMA key = 'x2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a'\")
conn.execute('CREATE TABLE t (id INTEGER)')
conn.execute('INSERT INTO t VALUES (1)')
conn.commit()
conn.close()
"
python -c "
import sqlite3
try:
    conn = sqlite3.connect('spike_test.db')
    conn.execute('SELECT * FROM t')
    print('FAIL: vanilla sqlite3 could read the encrypted file')
except Exception as e:
    print('OK: vanilla sqlite3 cannot read it —', type(e).__name__)
"
```
Expected: the second script prints `OK: vanilla sqlite3 cannot read it — DatabaseError` (or similar) — confirming the file is genuinely encrypted, not just a differently-named plaintext file. Delete `spike_test.db` after.

If `pip install sqlcipher3-binary` fails on this Windows environment (no prebuilt wheel available for the Python version in use), stop here and try `pip install pysqlcipher3` as a fallback, re-running the same smoke test. If **both** fail, this task's Step 5 escalation applies immediately — do not proceed to Task 2.

- [ ] **Step 2: Confirm PyInstaller can discover and bundle the native extension**

Create a minimal throwaway spec at `tools/spike_sqlcipher_build/spike.spec`:
```python
# -*- mode: python ; coding: utf-8 -*-
a = Analysis(['spike_app.py'], pathex=[], binaries=[], datas=[],
             hiddenimports=['sqlcipher3'], hookspath=[], hooksconfig={},
             runtime_hooks=[], excludes=[], noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='spike_app',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=True)
```
And `tools/spike_sqlcipher_build/spike_app.py`:
```python
import sqlcipher3 as sqlite3
conn = sqlite3.connect('frozen_spike_test.db')
conn.execute("PRAGMA key = 'x2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a'")
conn.execute('CREATE TABLE t (id INTEGER)')
conn.execute('INSERT INTO t VALUES (1)')
conn.commit()
print('SPIKE OK: wrote and read an encrypted DB from a frozen exe')
```

Run:
```bash
cd tools/spike_sqlcipher_build
pyinstaller spike.spec --noconfirm --clean
dist\spike_app\spike_app.exe
```
Expected: prints `SPIKE OK: wrote and read an encrypted DB from a frozen exe` with no missing-DLL error. A missing-DLL error at this point means `binaries=[]` needs an explicit entry — check whether the package ships a PyInstaller hook (`sqlcipher3/__pyinstaller/hook-sqlcipher3.py` or similar) or whether the native `.dll` needs to be manually added via `binaries=[('path/to/sqlcipher3.dll', '.')]`. Iterate on the spec until the frozen exe runs cleanly.

- [ ] **Step 3: Confirm `pywin32`'s DPAPI functions also survive freezing**

Same throwaway spec, add to `spike_app.py`:
```python
import win32crypt
blob = win32crypt.CryptProtectData(b'test-key-material', 'DentaCare encryption key',
                                    None, None, None, 0x4)  # CRYPTPROTECT_LOCAL_MACHINE
_, unprotected = win32crypt.CryptUnprotectData(blob, None, None, None, 0x4)
assert unprotected == b'test-key-material'
print('DPAPI SPIKE OK')
```
Add `'win32crypt', 'win32api'` to the spec's `hiddenimports`. Rebuild and rerun. Expected: `DPAPI SPIKE OK` with no import errors.

- [ ] **Step 4: Clean up the spike**

```bash
rm -rf tools/spike_sqlcipher_build
```
Add the confirmed-working package name and version floor to `requirements.txt`:
```
sqlcipher3-binary>=0.5.0
pywin32>=306
```
(Use the actual package name/version that worked in Step 1 — if `pysqlcipher3` was needed instead, use that name here and note it in the commit message, since it changes the import statement used in every subsequent task of this plan.)

- [ ] **Step 5: Escalation path if the spike fails**

If Steps 1-3 cannot be made to work after reasonable iteration (e.g. no Windows wheel exists for the SQLCipher binding at all, or PyInstaller fundamentally cannot bundle its native extension), **stop and report back to the user** rather than pushing forward with a broken approach or silently substituting a weaker one (like plaintext-with-a-warning). This would mean the spec's Decision 5 (SQLCipher) needs to be revisited — likely falling back to the "field-level encryption" or "OS-level (BitLocker)" options that were explicitly rejected during brainstorming, which is a real design decision for the user to make again with this new information, not something to decide unilaterally mid-implementation.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt
git commit -m "chore(security): add sqlcipher3-binary + pywin32, validated against the frozen build

Spiked SQLCipher's Windows wheel and pywin32's DPAPI functions against the
existing PyInstaller spec pattern before writing any production code against
them — both bundle and run cleanly in a frozen exe. Spike files deleted;
only the confirmed dependency versions are kept. First task of the
encryption-at-rest sub-project."
```

---

### Task 2: DPAPI key management module

**Files:**
- Create: `encryption_key.py`
- Test: `tests/test_encryption_key.py` (new)

**Interfaces:**
- Produces: `encryption_key.get_or_create_key(data_dir: Path) -> bytes` (returns the raw 32-byte key, generating + DPAPI-protecting it on first call, unprotecting it on every subsequent call), `encryption_key.KEY_FILENAME = 'encryption.key'`.
- Consumed by: Task 3 (`get_db_connection()`), Task 4 (migration).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_encryption_key.py`:

```python
"""DPAPI-protected encryption key generation and retrieval.

win32crypt is Windows-only and not meaningfully mockable across platforms in
a way that proves anything real, so these tests monkeypatch
encryption_key._protect/_unprotect with a reversible XOR stand-in that
exercises the exact same code paths (generate-once, persist, re-read,
never regenerate) without depending on the real Windows DPAPI call. The
real DPAPI call itself was already validated against a frozen build in
Task 1's spike and is a single one-line call in this module (Step 3) —
there is nothing else in it worth a live Windows-only test for.
"""
import pytest

import encryption_key


@pytest.fixture(autouse=True)
def fake_dpapi(monkeypatch):
    def _fake_protect(raw_bytes):
        return bytes(b ^ 0xFF for b in raw_bytes)

    def _fake_unprotect(blob):
        return bytes(b ^ 0xFF for b in blob)

    monkeypatch.setattr(encryption_key, '_protect', _fake_protect)
    monkeypatch.setattr(encryption_key, '_unprotect', _fake_unprotect)


def test_first_call_generates_and_persists_a_32_byte_key(tmp_path):
    key = encryption_key.get_or_create_key(tmp_path)
    assert len(key) == 32
    assert (tmp_path / encryption_key.KEY_FILENAME).exists()


def test_second_call_returns_the_same_key_not_a_new_one(tmp_path):
    key1 = encryption_key.get_or_create_key(tmp_path)
    key2 = encryption_key.get_or_create_key(tmp_path)
    assert key1 == key2


def test_key_file_on_disk_is_not_the_raw_key(tmp_path):
    key = encryption_key.get_or_create_key(tmp_path)
    on_disk = (tmp_path / encryption_key.KEY_FILENAME).read_bytes()
    assert on_disk != key  # must be the protected blob, not raw key material
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_encryption_key.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'encryption_key'`.

- [ ] **Step 3: Create `encryption_key.py`**

```python
"""DPAPI-protected encryption key for the clinic database.

The key is generated once and stored DPAPI-protected in machine scope
(CRYPTPROTECT_LOCAL_MACHINE) — not user scope — because the interactive
desktop app and the installed background Windows service may run under
different Windows execution contexts (the logged-in user vs. a service
account), and both must be able to unprotect the same key without
prompting anyone. See docs/superpowers/specs/2026-07-07-security-hardening-
rbac-design.md, Decision 6.
"""
import os
from pathlib import Path

KEY_FILENAME = 'encryption.key'
_KEY_BYTES = 32
_CRYPTPROTECT_LOCAL_MACHINE = 0x4


def _protect(raw_bytes):
    import win32crypt
    blob = win32crypt.CryptProtectData(
        raw_bytes, 'DentaCare DB encryption key', None, None, None,
        _CRYPTPROTECT_LOCAL_MACHINE)
    return bytes(blob)


def _unprotect(blob):
    import win32crypt
    _, raw = win32crypt.CryptUnprotectData(
        blob, None, None, None, _CRYPTPROTECT_LOCAL_MACHINE)
    return bytes(raw)


def get_or_create_key(data_dir: Path) -> bytes:
    """Return the raw 32-byte database encryption key, generating and
    DPAPI-protecting a new one on first call for this data_dir."""
    key_path = Path(data_dir) / KEY_FILENAME
    if key_path.exists():
        protected = key_path.read_bytes()
        return _unprotect(protected)
    raw_key = os.urandom(_KEY_BYTES)
    protected = _protect(raw_key)
    key_path.write_bytes(protected)
    return raw_key
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_encryption_key.py -v`
Expected: PASS, 3/3.

- [ ] **Step 5: Run full suite**

Run: `python -m pytest tests/ -q`
Expected: green — this module isn't wired into `dental_clinic.py` yet (that's Task 3), so nothing existing is affected.

- [ ] **Step 6: Commit**

```bash
git add encryption_key.py tests/test_encryption_key.py
git commit -m "feat(security): DPAPI-protected encryption key module

Machine-scope DPAPI so both the interactive app and the installed service
can unprotect the same key without a human typing a passphrase. Tests
exercise the generate-once/persist/reuse logic via a reversible stand-in
for the real (Windows-only) DPAPI calls. Part 2 of encryption-at-rest."
```

---

### Task 3: Wire encryption into `get_db_connection()`

**Files:**
- Modify: `dental_clinic.py:597-601` (`get_db_connection`)
- Test: `tests/test_encrypted_connection.py` (new)

**Interfaces:**
- Consumes: `encryption_key.get_or_create_key(data_dir)` from Task 2.
- Produces: `get_db_connection(with_row_factory=False)` now returns a connection to an **encrypted** database — every existing caller of this function (24 call sites already, confirmed by grep) keeps working with zero call-site changes, since the function's signature and return type (a connection object supporting the same `.cursor()`/`.execute()`/`.commit()`/`.close()` interface) don't change.

- [ ] **Step 1: Write the failing test**

Create `tests/test_encrypted_connection.py`:

```python
"""get_db_connection() must open the database through SQLCipher with the
DPAPI-protected key, so the resulting .db file cannot be read by vanilla
sqlite3."""
import sqlite3

import pytest

import dental_clinic


@pytest.fixture()
def encrypted_db(tmp_path, monkeypatch):
    test_db = tmp_path / 'enc_test.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(test_db))
    monkeypatch.setattr(dental_clinic, '_DATA_DIR', tmp_path)
    dental_clinic.init_database()
    return test_db


def test_database_file_is_not_readable_by_vanilla_sqlite3(encrypted_db):
    with pytest.raises(sqlite3.DatabaseError):
        conn = sqlite3.connect(str(encrypted_db))
        conn.execute('SELECT * FROM users').fetchall()


def test_get_db_connection_can_read_and_write(encrypted_db):
    conn = dental_clinic.get_db_connection()
    conn.execute("INSERT INTO app_settings (key, value) VALUES ('t', 'v')")
    conn.commit()
    row = conn.execute("SELECT value FROM app_settings WHERE key = 't'").fetchone()
    conn.close()
    assert row[0] == 'v'
```

(Note: `init_database()` itself must already use the encrypted path for this fixture to make sense — Task 5's codemod is what makes that true everywhere else in `dental_clinic.py`. For this task specifically, only `get_db_connection()` needs to be encrypted; if `init_database()` still uses a raw `sqlite3.connect(DB_NAME)` internally at this point in the plan, temporarily point this test's assertions at a connection opened via `get_db_connection()` for both setup and verification instead of relying on `init_database()` — adjust the fixture to call `get_db_connection()` directly for the setup INSERT if `init_database()` hasn't been converted yet at this point in the task sequence. Task 5 makes this moot by converting every call site including the ones inside `init_database()`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_encrypted_connection.py -v`
Expected: FAIL — the file is still plaintext, so `sqlite3.connect` + `SELECT` succeeds instead of raising.

- [ ] **Step 3: Update `get_db_connection()`**

Replace `dental_clinic.py:597-601`:

```python
def get_db_connection(with_row_factory=False):
    import sqlcipher3 as _sqlcipher  # see requirements.txt — name matches whichever
                                      # binding Task 1's spike confirmed working
    import encryption_key
    key = encryption_key.get_or_create_key(_DATA_DIR)
    conn = _sqlcipher.connect(DB_NAME)
    conn.execute(f"PRAGMA key = \"x'{key.hex()}'\"")
    if with_row_factory:
        conn.row_factory = _sqlcipher.Row
    return conn
```

(If Task 1's spike confirmed `pysqlcipher3` instead of `sqlcipher3-binary`, use `import pysqlcipher3.dbapi2 as _sqlcipher` here instead — match whatever import statement the spike actually validated, do not guess between them.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_encrypted_connection.py -v`
Expected: PASS, 2/2.

- [ ] **Step 5: Run full suite — expect failures, that's expected at this point**

Run: `python -m pytest tests/ -q`
Expected: **some existing tests will now fail** — anything that opens the test database directly with `sqlite3.connect(...)` (bypassing `get_db_connection()`) to set up fixtures or assert on rows will hit an encrypted file it can't read. This is expected and will be resolved by Task 5's codemod, not by this task. Do not attempt to fix these failures here — record the failing test count so Task 5's "full suite green again" step has a concrete number to compare against.

- [ ] **Step 6: Commit**

```bash
git add dental_clinic.py tests/test_encrypted_connection.py
git commit -m "feat(security): get_db_connection() opens the database via SQLCipher

Existing callers (24 sites) are unaffected — same function signature, same
returned connection interface. Direct sqlite3.connect(DB_NAME) call sites
elsewhere in the file will now fail against an encrypted DB; that's expected
and resolved in the next task, not this one. Part 3 of encryption-at-rest."
```

---

### Task 4: Migration — convert an existing plaintext database automatically

**Files:**
- Modify: `dental_clinic.py` — add a migration function near `init_database()`, call it once at process startup (find the exact startup sequence at `dental_clinic.py:8350-8391`, the `if __name__ == '__main__':` block, and the equivalent path the frozen service binary uses — check `dentacare_window.py` too, since the windowed launcher may call into this module's startup differently than the headless service)
- Test: `tests/test_encryption_migration.py` (new)

**Interfaces:**
- Consumes: `run_database_backup()` (existing, `dental_clinic.py:7343`), `encryption_key.get_or_create_key`, `get_db_connection`.
- Produces: `migrate_db_to_encrypted(db_path, data_dir) -> bool` (True if migration ran, False if the DB was already encrypted or didn't exist yet — both are no-ops, not errors).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_encryption_migration.py`:

```python
"""Automatic one-time migration of an existing plaintext clinic database to
SQLCipher encryption. Must never leave the clinic without a working,
openable database — every failure path restores the pre-migration backup."""
import sqlite3

import pytest

import dental_clinic


def _make_plaintext_db(path):
    conn = sqlite3.connect(str(path))
    conn.execute('CREATE TABLE patients (id INTEGER PRIMARY KEY, first_name TEXT)')
    conn.execute("INSERT INTO patients (first_name) VALUES ('Alice')")
    conn.execute("INSERT INTO patients (first_name) VALUES ('Bob')")
    conn.commit()
    conn.close()


def test_migrates_plaintext_db_and_preserves_all_rows(tmp_path, monkeypatch):
    db_path = tmp_path / 'clinic.db'
    _make_plaintext_db(db_path)
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db_path))
    monkeypatch.setattr(dental_clinic, '_DATA_DIR', tmp_path)
    monkeypatch.setattr(dental_clinic, 'BACKUP_DIR', tmp_path / 'backups')

    migrated = dental_clinic.migrate_db_to_encrypted(str(db_path), tmp_path)
    assert migrated is True

    with pytest.raises(sqlite3.DatabaseError):
        sqlite3.connect(str(db_path)).execute('SELECT * FROM patients').fetchall()

    conn = dental_clinic.get_db_connection()
    rows = conn.execute('SELECT first_name FROM patients ORDER BY id').fetchall()
    conn.close()
    assert [r[0] for r in rows] == ['Alice', 'Bob']


def test_already_encrypted_db_is_a_no_op(tmp_path, monkeypatch):
    db_path = tmp_path / 'clinic.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db_path))
    monkeypatch.setattr(dental_clinic, '_DATA_DIR', tmp_path)
    monkeypatch.setattr(dental_clinic, 'BACKUP_DIR', tmp_path / 'backups')
    dental_clinic.init_database()  # already creates it encrypted (Task 5)

    migrated = dental_clinic.migrate_db_to_encrypted(str(db_path), tmp_path)
    assert migrated is False


def test_nonexistent_db_is_a_no_op(tmp_path, monkeypatch):
    db_path = tmp_path / 'does_not_exist.db'
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db_path))
    monkeypatch.setattr(dental_clinic, '_DATA_DIR', tmp_path)
    migrated = dental_clinic.migrate_db_to_encrypted(str(db_path), tmp_path)
    assert migrated is False


def test_failure_mid_migration_restores_pre_migration_backup(tmp_path, monkeypatch):
    db_path = tmp_path / 'clinic.db'
    _make_plaintext_db(db_path)
    monkeypatch.setattr(dental_clinic, 'DB_NAME', str(db_path))
    monkeypatch.setattr(dental_clinic, '_DATA_DIR', tmp_path)
    monkeypatch.setattr(dental_clinic, 'BACKUP_DIR', tmp_path / 'backups')

    def _boom(*a, **kw):
        raise RuntimeError('simulated failure mid-export')

    monkeypatch.setattr(dental_clinic, '_sqlcipher_export', _boom)

    migrated = dental_clinic.migrate_db_to_encrypted(str(db_path), tmp_path)
    assert migrated is False  # migration did not silently "succeed"

    # The original plaintext DB must still be intact and readable — the
    # clinic is never left without a working database.
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute('SELECT first_name FROM patients ORDER BY id').fetchall()
    conn.close()
    assert [r[0] for r in rows] == ['Alice', 'Bob']
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_encryption_migration.py -v`
Expected: FAIL — `AttributeError: module 'dental_clinic' has no attribute 'migrate_db_to_encrypted'`.

- [ ] **Step 3: Implement the migration function**

Add to `dental_clinic.py`, near `run_database_backup()` (after line ~7391, wherever that function ends):

```python
def _is_plaintext_sqlite(path):
    """True if path opens successfully with vanilla sqlite3 and looks like a
    real database (has at least one table) — i.e. it predates encryption."""
    try:
        conn = sqlite3.connect(str(path))
        conn.execute("SELECT name FROM sqlite_master LIMIT 1")
        conn.close()
        return True
    except sqlite3.DatabaseError:
        return False


def _sqlcipher_export(plaintext_path, encrypted_path, key_hex):
    """Use SQLCipher's ATTACH + sqlcipher_export() to produce an encrypted
    copy of a plaintext database. Isolated into its own function so tests can
    monkeypatch a failure here without needing a real SQLCipher error."""
    import sqlcipher3 as _sqlcipher  # match Task 1/3's confirmed import
    conn = _sqlcipher.connect(str(encrypted_path))
    conn.execute(f"PRAGMA key = \"x'{key_hex}'\"")
    conn.execute(f"ATTACH DATABASE '{plaintext_path}' AS plaintext KEY ''")
    conn.execute("SELECT sqlcipher_export('main', 'plaintext')")
    conn.execute("DETACH DATABASE plaintext")
    conn.commit()
    conn.close()


def migrate_db_to_encrypted(db_path, data_dir):
    """One-time migration: if db_path is an existing plaintext SQLite
    database, back it up, encrypt it in place, verify row counts, and
    replace the original. Returns True if a migration actually ran, False
    for every no-op case (already encrypted, or doesn't exist yet — a brand
    new install's DB is created encrypted from the start by init_database()).
    Never leaves db_path in a broken or partially-migrated state: on any
    failure, the original plaintext file is left completely untouched (the
    encrypted copy is built in a temp file first, never in place)."""
    import tempfile
    import shutil as _shutil

    if not os.path.exists(db_path):
        return False
    if not _is_plaintext_sqlite(db_path):
        return False  # already encrypted (or corrupt — leave it for the operator, don't touch)

    backups = run_database_backup()
    if not backups:
        print('⚠️  Encryption migration skipped: could not create a safety backup first.')
        return False

    key = encryption_key.get_or_create_key(data_dir)
    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.db', dir=os.path.dirname(str(db_path)) or '.')
    os.close(tmp_fd)
    os.remove(tmp_path)  # sqlcipher_export needs to create this file itself
    try:
        _sqlcipher_export(db_path, tmp_path, key.hex())
        # Verify row counts match across every user table before trusting the copy.
        orig_conn = sqlite3.connect(str(db_path))
        tables = [r[0] for r in orig_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        orig_counts = {t: orig_conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}
        orig_conn.close()

        import sqlcipher3 as _sqlcipher
        new_conn = _sqlcipher.connect(tmp_path)
        new_conn.execute(f"PRAGMA key = \"x'{key.hex()}'\"")
        new_counts = {t: new_conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}
        new_conn.close()

        if orig_counts != new_counts:
            raise RuntimeError(f'Row count mismatch after migration: {orig_counts} != {new_counts}')

        _shutil.move(tmp_path, str(db_path))
        print(f'🔒 Database encrypted at rest ({sum(orig_counts.values())} rows verified).')
        return True
    except Exception as exc:  # noqa: BLE001 - any failure here must restore, not half-apply
        print(f'⚠️  Encryption migration failed ({exc}); restoring pre-migration backup.')
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        _shutil.copy2(backups[0], str(db_path))
        return False
```

Wire the call in at startup. In the `if __name__ == '__main__':` block (`dental_clinic.py:8350`), find where `init_database()` is called (line 8388) and add the migration call **before** it (migrate first, then `init_database()` runs its normal `CREATE TABLE IF NOT EXISTS` migrations against the now-encrypted file):

```python
    if not CLOUD_MODE:  # DPAPI/SQLCipher migration is desktop/service-only, never cloud
        migrate_db_to_encrypted(DB_NAME, _DATA_DIR)
    init_database()
```

Check `dentacare_window.py` for whether it calls `init_database()` itself on a separate path (the windowed launcher may spawn the Flask app differently than the `__main__` block) — run `grep -n "init_database" dentacare_window.py` and add the same migration call there if it has its own independent startup sequence, so both the interactive window and the headless service migrate identically.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_encryption_migration.py -v`
Expected: PASS, 4/4.

- [ ] **Step 5: Run full suite**

Run: `python -m pytest tests/ -q`
Expected: still the same pre-existing failures from Task 3 (tests bypassing `get_db_connection()`) — Task 5 resolves those, not this one.

- [ ] **Step 6: Commit**

```bash
git add dental_clinic.py tests/test_encryption_migration.py
git commit -m "feat(security): automatic migration of existing plaintext DBs to encrypted

Backs up first, exports via SQLCipher's ATTACH+sqlcipher_export(), verifies
row counts match across every table, then atomically replaces the original.
Any failure at any step restores the pre-migration backup — the clinic is
never left without a working database. Gated to non-CLOUD_MODE only. Part 4
of encryption-at-rest."
```

---

### Task 5: Convert every remaining direct connection call site

**Files:**
- Modify: `dental_clinic.py` — all remaining `sqlite3.connect(DB_NAME)` (71 sites) and `sqlite3.connect(str(DB_NAME))` (8 sites) call sites, confirmed by exact count during planning (`python -c "print(open('dental_clinic.py').read().count(...))"`).

**Interfaces:**
- Consumes: `get_db_connection()` (Task 3).
- Produces: nothing new — this task's deliverable is "zero raw connections to the primary DB remain outside `get_db_connection()`," verified mechanically, not a new function.

- [ ] **Step 1: Confirm the exact current count before touching anything**

Run:
```bash
python -c "
data = open('dental_clinic.py', encoding='utf-8').read()
print('DB_NAME direct:', data.count('sqlite3.connect(DB_NAME)'))
print('str(DB_NAME) direct:', data.count('sqlite3.connect(str(DB_NAME))'))
"
```
Expected output at the start of this task: `DB_NAME direct: 71` and `str(DB_NAME) direct: 8` (the counts confirmed during planning on 2026-07-07 — if the numbers differ because other work landed on this file since, that's fine, just note the actual starting counts here instead of assuming these exact ones).

- [ ] **Step 2: Mechanical replacement**

Every call site follows one of two shapes today:
```python
conn = sqlite3.connect(DB_NAME)
```
or
```python
conn = sqlite3.connect(DB_NAME)
conn.row_factory = sqlite3.Row
```
Replace with, respectively:
```python
conn = get_db_connection()
```
or
```python
conn = get_db_connection(with_row_factory=True)
```
(dropping the now-redundant separate `conn.row_factory = sqlite3.Row` line when the call site sets it immediately after connecting — check each site rather than blindly stripping a line that might not immediately follow in every case).

Do this with a scripted pass rather than 79 manual edits — write a small one-off Python script (not committed) that:
1. Reads `dental_clinic.py`.
2. Replaces every `conn = sqlite3.connect(DB_NAME)\n    conn.row_factory = sqlite3.Row` (and the `str(DB_NAME)` variant) with `conn = get_db_connection(with_row_factory=True)`.
3. Replaces every remaining plain `sqlite3.connect(DB_NAME)` / `sqlite3.connect(str(DB_NAME))` with `get_db_connection()`.
4. Writes the file back.

Then manually review the diff (`git diff dental_clinic.py`) for any call site the script's exact-string matching missed (e.g. unusual whitespace, or a connect immediately followed by something other than a plain `.row_factory =` line) and fix those by hand.

**Do not touch**: any `sqlite3.connect(MASTER_DB_PATH)` site, and the two `sqlite3.connect(...)` calls this task's own code depends on for correctness — `_is_plaintext_sqlite()` and the verification step inside `migrate_db_to_encrypted()` (Task 4) **must** keep using vanilla `sqlite3.connect` deliberately, since their entire job is to test whether the file is still plaintext / read the pre-migration plaintext copy. Grep for `_is_plaintext_sqlite\|orig_conn = sqlite3.connect` before running the scripted replacement to confirm the script's target string doesn't accidentally match inside those two functions (they use `sqlite3.connect(str(db_path))` / `sqlite3.connect(str(plaintext_path))` with a local parameter name, not the literal `DB_NAME` global, so the exact-string replacement described above should not match them — verify this after running the script, don't just assume it).

- [ ] **Step 3: Verify zero raw call sites remain (outside the deliberate exceptions)**

Run:
```bash
python -c "
data = open('dental_clinic.py', encoding='utf-8').read()
print('remaining DB_NAME direct:', data.count('sqlite3.connect(DB_NAME)'))
print('remaining str(DB_NAME) direct:', data.count('sqlite3.connect(str(DB_NAME))'))
"
```
Expected: both `0`.

- [ ] **Step 4: Run full suite — this is the real verification for this task**

Run: `python -m pytest tests/ -q`
Expected: green, and specifically the tests that started failing in Task 3 (tests bypassing `get_db_connection()` in their own fixtures to set up data — those test fixtures connect to the file directly, so they'll need the SAME treatment: any test fixture that does `sqlite3.connect(dental_clinic.DB_NAME)` to seed data must be updated to use `dental_clinic.get_db_connection()` instead). Grep the test suite for the same pattern and fix every hit:
```bash
grep -rln "sqlite3.connect(dental_clinic.DB_NAME)\|sqlite3.connect(str(dental_clinic.DB_NAME))" tests/
```
Update each matched test file's direct connects the same way as the production code (Step 2's pattern), except tests that are **specifically** testing that the file is encrypted (Task 3's `test_database_file_is_not_readable_by_vanilla_sqlite3`, Task 4's `test_migrates_plaintext_db_and_preserves_all_rows`) must keep their deliberate vanilla `sqlite3.connect` call — that's the assertion, not a bug.

- [ ] **Step 5: Commit**

```bash
git add dental_clinic.py tests/
git commit -m "refactor(security): route every DB_NAME connection through get_db_connection()

Mechanical conversion of all remaining direct sqlite3.connect(DB_NAME) call
sites (dental_clinic.py + any test fixtures that connected directly) so the
whole app opens the encrypted database consistently. MASTER_DB_PATH
(cloud-only) and the migration's own plaintext-detection calls are
deliberately left untouched. Part 5 of encryption-at-rest — the full
existing suite is the primary regression net for this change."
```

---

### Task 6: PyInstaller spec — bundle the new dependencies

**Files:**
- Modify: `DentaCare.spec` — `COMMON_HIDDEN` list (around line 15-45)

**Interfaces:**
- Consumes: whatever Task 1's spike confirmed about hidden-imports/binaries requirements for the chosen SQLCipher binding and `pywin32`.

- [ ] **Step 1: Add hidden imports**

In `DentaCare.spec`, add to `COMMON_HIDDEN` (both binaries need this — the service reads/writes the DB directly, and the window launcher's UI code also calls into `dental_clinic` functions):

```python
    # Encryption-at-rest (see docs/superpowers/plans/2026-07-07-security-encryption-at-rest.md).
    'sqlcipher3',            # or 'pysqlcipher3', 'pysqlcipher3.dbapi2' — match Task 1's confirmed import
    'win32crypt',
    'win32api',
```

If Task 1's Step 2 spike needed an explicit `binaries=[...]` entry for the native SQLCipher DLL (rather than PyInstaller auto-discovering it), add that same entry to both `service_a = Analysis(...)` and `window_a = Analysis(...)` binaries lists in this file — copy the exact working entry from the spike's `spike.spec`, don't re-derive it from scratch.

- [ ] **Step 2: Full local rebuild + smoke test**

Run:
```bash
pyinstaller DentaCare.spec --noconfirm --clean
dist\DentaCareService\DentaCareService.exe
```
(in a separate terminal/timeout-bounded run, since this starts a server) — confirm it starts without an import error, then Ctrl+C it. Then:
```bash
dist\DentaCare\DentaCare.exe
```
Confirm the window opens and the portal loads (login page reachable), confirming the encrypted-DB startup path (Task 4's migration call) runs cleanly in the actual frozen binary, not just under `python -m pytest`.

- [ ] **Step 3: Run full suite one more time**

Run: `python -m pytest tests/ -q`
Expected: green — this task only changes the build spec, not application code.

- [ ] **Step 4: Commit**

```bash
git add DentaCare.spec
git commit -m "chore(security): bundle SQLCipher + pywin32 in the frozen build

Hidden-imports (and binaries entry, if the Task 1 spike needed one) added
to both DentaCareService.exe and DentaCare.exe. Frozen-build smoke test
confirms the encrypted-DB startup path runs cleanly outside pytest, not
just under python -m pytest. Final task of the security sub-project —
CSP, RBAC, and encryption-at-rest are now all shipped."
```

## Self-review notes

- Spec coverage: Decisions 5 (SQLCipher whole-DB), 6 (DPAPI machine-scope), 7 (automatic migration), and every component in Architecture › Encryption (key lifecycle, connection helper, migration function, mechanical call-site conversion) each have a task. The out-of-scope items (MASTER_DB_PATH/CLOUD_MODE, db_merge.py, serial_admin.py) are called out explicitly in Global Constraints so a future reader doesn't mistake their omission for an oversight.
- Placeholder scan: Task 1 is the one task whose *outcome* is genuinely unknown (which exact package name wins), but every step in it is a complete, runnable, concrete action with an explicit pass/fail check and an explicit escalation path on failure — this is a spike, not a placeholder. Every other task has complete code.
- Type/name consistency: `get_or_create_key`, `migrate_db_to_encrypted`, `_sqlcipher_export`, `_is_plaintext_sqlite` are named identically everywhere referenced across Tasks 2-5. The import name (`sqlcipher3` vs `pysqlcipher3`) is explicitly flagged in three places (Task 3, Task 4, Task 6) as "match whatever Task 1 confirmed" rather than silently assuming one — this is a genuine cross-task dependency on a spike result, documented rather than guessed.
- This is the highest-risk of the 3 PRs, exactly as the spec ordered it last — every task ends with "run the full suite," and Task 5 in particular calls out that some failures are *expected* between Task 3 and Task 5 (not a regression to panic about mid-sequence), which matters for whoever executes this plan task-by-task.
