import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../state/app_state.dart';
import '../services/connectivity_sync_service.dart';
import '../utils/sync_banner.dart';

/// Thin banner under the app bar that announces a sync *change* and then gets
/// out of the way. It flashes the new state (Synced / Offline / Syncing…) and
/// auto-hides a few seconds later instead of lingering forever or re-flashing
/// on every routine cycle (de-flicker is also enforced at the service, which
/// drops identical consecutive emissions).
class SyncStatusBar extends StatefulWidget {
  const SyncStatusBar({super.key});

  @override
  State<SyncStatusBar> createState() => _SyncStatusBarState();
}

class _SyncStatusBarState extends State<SyncStatusBar> {
  ConnectivitySyncService? _sync;
  StreamSubscription<SyncStatus>? _sub;
  Timer? _hideTimer;

  SyncStatus? _shown; // null = hidden
  String? _shownMsg;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final sync = context.read<AppState>().sync;
    if (identical(sync, _sync)) return;
    _sub?.cancel();
    _sync = sync;
    _apply(sync.status, sync.statusMessage);
    _sub = sync.statusStream.listen((s) => _apply(s, sync.statusMessage));
  }

  void _apply(SyncStatus status, String? msg) {
    final behavior = syncBannerBehavior(status);
    _hideTimer?.cancel();
    if (!behavior.show) {
      if (mounted) setState(() => _shown = null);
      return;
    }
    if (mounted) {
      setState(() {
        _shown = status;
        _shownMsg = msg;
      });
    }
    final hideAfter = behavior.autoHide;
    if (hideAfter != null) {
      _hideTimer = Timer(hideAfter, () {
        if (mounted) setState(() => _shown = null);
      });
    }
  }

  @override
  void dispose() {
    _hideTimer?.cancel();
    _sub?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final status = _shown;
    if (status == null) return const SizedBox.shrink();
    final (bg, icon, msg) = _resolve(status, _shownMsg);
    return AnimatedContainer(
      duration: const Duration(milliseconds: 300),
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      color: bg,
      child: Row(
        children: [
          icon,
          const SizedBox(width: 8),
          Expanded(
              child: Text(msg,
                  style: const TextStyle(
                      color: Colors.white,
                      fontSize: 12,
                      fontWeight: FontWeight.w600))),
        ],
      ),
    );
  }

  (Color, Widget, String) _resolve(SyncStatus s, String? msg) {
    switch (s) {
      case SyncStatus.syncing:
        return (
          const Color(0xFF1D7FB7),
          const SizedBox(
              width: 14,
              height: 14,
              child: CircularProgressIndicator(
                  color: Colors.white, strokeWidth: 2)),
          msg ?? 'Syncing…',
        );
      case SyncStatus.offline:
        return (
          const Color(0xFFD89E1F),
          const Icon(Icons.bluetooth_searching, color: Colors.white, size: 16),
          msg ?? 'Offline — tap Settings to sync via Bluetooth',
        );
      case SyncStatus.error:
        return (
          const Color(0xFFD9434E),
          const Icon(Icons.sync_problem, color: Colors.white, size: 16),
          msg ?? 'Sync failed',
        );
      case SyncStatus.synced:
        return (
          const Color(0xFF1F9A5F),
          const Icon(Icons.cloud_done_outlined, color: Colors.white, size: 16),
          msg ?? 'Synced',
        );
      default:
        return (Colors.grey, const SizedBox.shrink(), '');
    }
  }
}
