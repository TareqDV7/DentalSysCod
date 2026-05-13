import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../state/app_state.dart';
import '../services/connectivity_sync_service.dart';

class SyncStatusBar extends StatelessWidget {
  const SyncStatusBar({super.key});

  @override
  Widget build(BuildContext context) {
    final sync = context.watch<AppState>().sync;

    return StreamBuilder<SyncStatus>(
      stream: sync.statusStream,
      initialData: sync.status,
      builder: (context, snapshot) {
        final status = snapshot.data ?? SyncStatus.idle;
        if (status == SyncStatus.idle) {
          return const SizedBox.shrink();
        }
        final (bg, icon, msg) = _resolve(status, sync.statusMessage);
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
      },
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
