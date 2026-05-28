# Provision an Incoming SPP (Serial Port Profile) COM port on Windows so the
# Bluetooth-SPP sync path works without the customer touching Windows BT
# settings. Idempotent: if any Incoming SPP port already exists, exits 0
# without changes.
#
# Run by the Inno Setup installer with elevated privileges. Exit code 0 on
# success, 2 if user action is required, 1 on fatal error (logged to the
# installer log either way).

$ErrorActionPreference = 'Stop'

function Write-Log($msg) {
    $line = "[$([DateTime]::UtcNow.ToString('o'))] $msg"
    Write-Host $line
}

try {
    # Detect existing Incoming SPP COM ports. Windows registers each one under
    # HKLM\HARDWARE\DEVICEMAP\SERIALCOMM with a device path that includes
    # 'BthModem' (the Bluetooth modem class enumerator for incoming SPP ports).
    # Outgoing SPP ports use a different enumerator path that doesn't include
    # 'BthModem' — so the heuristic is reliable.
    $regPath = 'HKLM:\HARDWARE\DEVICEMAP\SERIALCOMM'
    $ports = Get-ItemProperty -Path $regPath -ErrorAction SilentlyContinue
    $btIncomingExists = $false
    if ($ports) {
        foreach ($name in $ports.PSObject.Properties.Name) {
            if ($name -like '*BthModem*') {
                $btIncomingExists = $true
                $val = $ports.$name
                Write-Log "Found existing Incoming SPP entry: $name -> $val"
            }
        }
    }

    if ($btIncomingExists) {
        Write-Log 'Incoming SPP COM port already provisioned. Nothing to do.'
        exit 0
    }

    # No incoming SPP port found. Reliable programmatic creation of one without
    # third-party drivers is not supported on Windows 10/11 — the API surface
    # that worked on Windows 7 (DEVPROP_Bluetooth_Service) is no longer
    # documented. Fall back to opening the Bluetooth COM Ports dialog so the
    # user can click Add -> Incoming with one click. The Inno Setup installer
    # surfaces a follow-up message box explaining this.
    Write-Log 'No Incoming SPP found. Opening Bluetooth COM Ports dialog so'
    Write-Log 'the user can add the port via Add -> Incoming.'

    # bthprops.cpl on Windows 10/11 opens the Bluetooth settings dialog. The
    # COM Ports tab is one click away from there.
    Start-Process -FilePath 'rundll32.exe' -ArgumentList 'bthprops.cpl' -WindowStyle Normal
    exit 2  # 2 = user-action-required; installer logs this and continues
}
catch {
    Write-Log "FATAL: $($_.Exception.Message)"
    exit 1
}
