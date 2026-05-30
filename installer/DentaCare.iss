; DentaCare Inno Setup installer.
;
; Build with: ISCC.exe installer\DentaCare.iss
; Produces:   installer\Output\DentaCare-Setup.exe
;
; Requires:   dist\staging\ populated by rebuild.bat first.

#define MyAppName        "DentaCare"
#define MyAppVersion     "1.1.0"
#define MyAppPublisher   "DentaCare"
#define MyAppExeName     "DentaCare.exe"
#define MyServiceExeName "DentaCareService.exe"
#define StagingDir       "..\dist\staging"

[Setup]
AppId={{B8F4D1A2-7B62-4E3D-9F8C-DentaCare00001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=DentaCare-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=..\DentaCare.ico
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
LicenseFile=..\LICENSE

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";  Description: "Create a desktop shortcut";       GroupDescription: "Shortcuts:";  Flags: unchecked
Name: "autostart";    Description: "Launch DentaCare window at logon"; GroupDescription: "Startup:";

[Files]
Source: "{#StagingDir}\{#MyAppExeName}";        DestDir: "{app}"; Flags: ignoreversion
Source: "{#StagingDir}\{#MyServiceExeName}";    DestDir: "{app}"; Flags: ignoreversion
Source: "{#StagingDir}\nssm.exe";               DestDir: "{app}"; Flags: ignoreversion
Source: "{#StagingDir}\DentaCare.PNG";          DestDir: "{app}"; Flags: ignoreversion
Source: "..\installer\provision_bt.ps1";        DestDir: "{app}\installer"; Flags: ignoreversion
Source: "..\installer\MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall ignoreversion

[Dirs]
Name: "{commonappdata}\DentaCare";          Permissions: system-full
Name: "{commonappdata}\DentaCare\uploads";  Permissions: system-full
Name: "{commonappdata}\DentaCare\backups";  Permissions: system-full
Name: "{commonappdata}\DentaCare\logs";     Permissions: system-full

[Icons]
Name: "{group}\{#MyAppName}";   Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Machine-wide autostart. Under an admin (machine-wide) install, HKCU resolves to
; the elevated context rather than the logged-in user's hive, so an HKCU Run value
; silently fails to autostart for the actual user. HKLM Run autostarts for whoever
; logs in — the right behaviour for a single-workstation clinic appliance.
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "DentaCare"; ValueData: """{app}\{#MyAppExeName}"""; \
    Flags: uninsdeletevalue; Tasks: autostart

[Run]
; 1. Install WebView2 if missing (the bootstrapper no-ops if already present).
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; \
    Parameters: "/silent /install"; \
    StatusMsg: "Installing Microsoft Edge WebView2 runtime..."; \
    Check: NeedsWebView2

; 2. Register and start the NSSM service.
; (BT setup no longer runs here — the native AF_BTH listener in dental_clinic.py
; publishes its own SPP SDP record at runtime, so no Incoming COM port is
; required. installer\provision_bt.ps1 still ships in {app}\installer for the
; rare COM-port fallback case; an admin can run it by hand if needed.)
Filename: "{app}\nssm.exe"; Parameters: "install DentaCare ""{app}\{#MyServiceExeName}"""; Flags: runhidden
Filename: "{app}\nssm.exe"; Parameters: "set DentaCare AppDirectory ""{commonappdata}\DentaCare"""; Flags: runhidden
Filename: "{app}\nssm.exe"; Parameters: "set DentaCare AppStdout ""{commonappdata}\DentaCare\logs\service.stdout.log"""; Flags: runhidden
Filename: "{app}\nssm.exe"; Parameters: "set DentaCare AppStderr ""{commonappdata}\DentaCare\logs\service.stderr.log"""; Flags: runhidden
Filename: "{app}\nssm.exe"; Parameters: "set DentaCare AppRotateFiles 1"; Flags: runhidden
Filename: "{app}\nssm.exe"; Parameters: "set DentaCare AppRotateBytes 10485760"; Flags: runhidden
Filename: "{app}\nssm.exe"; Parameters: "set DentaCare AppEnvironmentExtra CLINIC_HEADLESS=1 CLINIC_HOST=0.0.0.0 CLINIC_PORT=5000 CLINIC_DATA_DIR={commonappdata}\DentaCare"; Flags: runhidden
Filename: "{app}\nssm.exe"; Parameters: "set DentaCare Start SERVICE_AUTO_START"; Flags: runhidden
Filename: "{app}\nssm.exe"; Parameters: "set DentaCare ObjectName LocalSystem"; Flags: runhidden
Filename: "{app}\nssm.exe"; Parameters: "start DentaCare"; Flags: runhidden

; 3. Launch the window on install completion.
Filename: "{app}\{#MyAppExeName}"; Description: "Launch DentaCare"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
function NeedsWebView2: Boolean;
var
  Version: string;
begin
  // WebView2 runtime registers under HKLM if present. Two possible paths
  // depending on machine-wide or per-user install.
  Result := not (
    RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version)
    or RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version)
  );
end;

function FindLegacyDatabase: string;
var
  FindRec: TFindRec;
  UsersDir, Base, Cand: string;
begin
  Result := '';
  // Some users moved the portable folder to the drive root.
  if FileExists('C:\DentaCare\dental_clinic.db') then begin
    Result := 'C:\DentaCare\dental_clinic.db';
    exit;
  end;
  // Setup runs elevated, so per-user constants like {userdesktop}/{userdocs}
  // resolve to the elevated context rather than the logged-in user's profile —
  // that is why an earlier {userdesktop} lookup silently missed the DB. Scan
  // {sd}\Users directly instead; this finds the file in whichever profile owns
  // it and also covers OneDrive-redirected Desktops.
  UsersDir := ExpandConstant('{sd}\Users');
  if FindFirst(UsersDir + '\*', FindRec) then begin
    try
      repeat
        if (FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY <> 0)
           and (FindRec.Name <> '.') and (FindRec.Name <> '..') then begin
          Base := UsersDir + '\' + FindRec.Name;
          Cand := Base + '\Desktop\dental_clinic.db';
          if FileExists(Cand) then begin Result := Cand; exit; end;
          Cand := Base + '\OneDrive\Desktop\dental_clinic.db';
          if FileExists(Cand) then begin Result := Cand; exit; end;
          Cand := Base + '\Documents\dental_clinic.db';
          if FileExists(Cand) then begin Result := Cand; exit; end;
        end;
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;
end;

procedure CopyLegacyDatabase;
var
  SrcPath, DstPath: string;
  RespCode: Integer;
begin
  DstPath := ExpandConstant('{commonappdata}\DentaCare\dental_clinic.db');
  Log('CopyLegacyDatabase: DstPath=' + DstPath + ' exists=' + IntToStr(Ord(FileExists(DstPath))));
  if FileExists(DstPath) then exit;  // Already migrated or fresh install.

  SrcPath := FindLegacyDatabase;
  Log('CopyLegacyDatabase: legacy DB found=[' + SrcPath + ']');
  if SrcPath = '' then exit;

  RespCode := MsgBox(
    'Existing DentaCare database found:' + #13#10 + #13#10 +
    SrcPath + #13#10 + #13#10 +
    'Copy it to the new location so your patient data carries over?' + #13#10 +
    '(Original will be left in place as a backup.)',
    mbConfirmation, MB_YESNO or MB_DEFBUTTON1);
  if RespCode = IDYES then begin
    if CopyFile(SrcPath, DstPath, False) then
      Log('CopyLegacyDatabase: copied OK')
    else
      Log('CopyLegacyDatabase: CopyFile FAILED');
  end;
end;

procedure StopRunningInstance;
var
  ResultCode: Integer;
begin
  // On an upgrade the previous service and window still hold DentaCareService.exe
  // and DentaCare.exe open, so the file copy fails with "DeleteFile failed, code 5
  // (access denied)". Stop + remove the service (recreated fresh by [Run]) and
  // close the window before any file is replaced. All no-ops on a first install,
  // where {app}\nssm.exe does not yet exist and no window is running.
  if FileExists(ExpandConstant('{app}\nssm.exe')) then begin
    Exec(ExpandConstant('{app}\nssm.exe'), 'stop DentaCare', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec(ExpandConstant('{app}\nssm.exe'), 'remove DentaCare confirm', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM DentaCare.exe /F', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  // ssInstall fires just before files are copied: free any locked binaries.
  if CurStep = ssInstall then begin
    StopRunningInstance;
  end;
  // ssPostInstall runs after files are copied but before [Run] steps. We
  // migrate the DB here so the service starts with the customer's data
  // already in the new location.
  if CurStep = ssPostInstall then begin
    CopyLegacyDatabase;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode, i, Response: Integer;
  NssmPath, SvcExe: string;
begin
  if CurUninstallStep = usUninstall then begin
    // usUninstall fires before Inno removes {app}. Tear the service down here so
    // the binaries are unlocked first. Done in code (not [UninstallRun]) so the
    // poll-delete below runs in a guaranteed order after stop/remove.
    NssmPath := ExpandConstant('{app}\nssm.exe');
    SvcExe   := ExpandConstant('{app}\DentaCareService.exe');
    // Close the running window so DentaCare.exe is unlocked.
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM DentaCare.exe /F', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    if FileExists(NssmPath) then begin
      Exec(NssmPath, 'stop DentaCare', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      Exec(NssmPath, 'remove DentaCare confirm', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end;
    // The SCM can keep nssm.exe + DentaCareService.exe locked for a few seconds
    // after removal. Poll-delete them so Inno's file pass doesn't race the SCM
    // and leave orphaned binaries behind.
    for i := 1 to 20 do begin
      if ((not FileExists(SvcExe)) or DeleteFile(SvcExe))
         and ((not FileExists(NssmPath)) or DeleteFile(NssmPath)) then
        break;
      Sleep(500);
    end;
  end;

  if CurUninstallStep = usPostUninstall then begin
    Response := MsgBox(
      'Remove DentaCare clinic data?' + #13#10 + #13#10 +
      'This will permanently delete all patient records, appointments, and backups in:' + #13#10 +
      ExpandConstant('{commonappdata}\DentaCare') + #13#10 + #13#10 +
      'Click NO to keep the data (recommended).',
      mbConfirmation, MB_YESNO or MB_DEFBUTTON2);
    if Response = IDYES then begin
      DelTree(ExpandConstant('{commonappdata}\DentaCare'), True, True, True);
    end;
  end;
end;
