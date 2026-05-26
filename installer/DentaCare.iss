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
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "DentaCare"; ValueData: """{app}\{#MyAppExeName}"""; \
    Flags: uninsdeletevalue; Tasks: autostart

[Run]
; 1. Install WebView2 if missing (the bootstrapper no-ops if already present).
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; \
    Parameters: "/silent /install"; \
    StatusMsg: "Installing Microsoft Edge WebView2 runtime..."; \
    Check: NeedsWebView2

; 2. Provision the Bluetooth Incoming SPP COM port.
Filename: "powershell.exe"; \
    Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\installer\provision_bt.ps1"""; \
    StatusMsg: "Configuring Bluetooth sync..."; \
    Flags: runhidden

; 3. Register and start the NSSM service.
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

; 4. Launch the window on install completion.
Filename: "{app}\{#MyAppExeName}"; Description: "Launch DentaCare"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\nssm.exe"; Parameters: "stop DentaCare";           Flags: runhidden
Filename: "{app}\nssm.exe"; Parameters: "remove DentaCare confirm"; Flags: runhidden

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

procedure CopyLegacyDatabase;
var
  CandidatePaths: array of string;
  i: Integer;
  SrcPath, DstPath: string;
  RespCode: Integer;
begin
  // Common legacy locations where the portable .exe stored its DB:
  //   - Desktop folder of the user who ran the installer
  //   - Documents
  //   - C:\DentaCare (some users move the folder to root)
  SetArrayLength(CandidatePaths, 3);
  CandidatePaths[0] := ExpandConstant('{userdesktop}\dental_clinic.db');
  CandidatePaths[1] := ExpandConstant('{userdocs}\dental_clinic.db');
  CandidatePaths[2] := 'C:\DentaCare\dental_clinic.db';

  DstPath := ExpandConstant('{commonappdata}\DentaCare\dental_clinic.db');

  if FileExists(DstPath) then exit;  // Already migrated or fresh install.

  for i := 0 to GetArrayLength(CandidatePaths) - 1 do begin
    SrcPath := CandidatePaths[i];
    if FileExists(SrcPath) then begin
      RespCode := MsgBox(
        'Existing DentaCare database found:' + #13#10 + #13#10 +
        SrcPath + #13#10 + #13#10 +
        'Copy it to the new location so your patient data carries over?' + #13#10 +
        '(Original will be left in place as a backup.)',
        mbConfirmation, MB_YESNO or MB_DEFBUTTON1);
      if RespCode = IDYES then begin
        FileCopy(SrcPath, DstPath, False);
      end;
      exit;  // Stop at first found, regardless of choice.
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  // ssPostInstall runs after files are copied but before [Run] steps. We
  // migrate the DB here so the service starts with the customer's data
  // already in the new location.
  if CurStep = ssPostInstall then begin
    CopyLegacyDatabase;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Response: Integer;
begin
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
