import 'api_client.dart';

/// The desktop is the license authority; the phone DERIVES this state over the
/// LAN from GET /api/license/gate. It never activates a license itself.
sealed class LicenseGateState {
  const LicenseGateState();
}

final class GateActive extends LicenseGateState {
  const GateActive();
}

final class GateGrace extends LicenseGateState {
  const GateGrace(this.graceUntil);
  final String graceUntil;
}

final class GateViewOnly extends LicenseGateState {
  const GateViewOnly();
}

final class GateUnlicensed extends LicenseGateState {
  const GateUnlicensed();
}

/// Desktop unreachable / unparseable — the app stays usable (offline-tolerant);
/// it only gates on an explicit view_only/unlicensed answer.
final class GateUnknown extends LicenseGateState {
  const GateUnknown();
}

/// Pure, server-free mapping so it is unit-testable without a camera or network.
LicenseGateState mapGateState(Map<String, dynamic> json) {
  switch ((json['state'] ?? '').toString()) {
    case 'active':
      return const GateActive();
    case 'grace':
      return GateGrace((json['grace_until'] ?? '').toString());
    case 'view_only':
      return const GateViewOnly();
    case 'unlicensed':
      return const GateUnlicensed();
    default:
      return const GateUnknown();
  }
}

class LicenseGateService {
  LicenseGateService([ApiClient? api]) : _api = api ?? ApiClient();
  final ApiClient _api;

  Future<LicenseGateState> fetchGate({
    required String baseUrl,
    String? deviceToken,
  }) async {
    try {
      final data = await _api.getJson(
        baseUrl: baseUrl,
        path: '/api/license/gate',
        deviceToken: deviceToken,
      );
      return mapGateState(data);
    } on Object {
      return const GateUnknown();
    }
  }
}
