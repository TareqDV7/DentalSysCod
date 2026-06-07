import '../services/connectivity_sync_service.dart';

/// How the top sync banner should present a given [SyncStatus].
///
/// The banner announces a *change* and then gets out of the way — it must not
/// linger showing "Synced" forever, nor flicker on every routine cycle. So
/// terminal states are shown briefly and then auto-hide; `syncing` stays up
/// until it resolves (it always does, quickly); `idle` is not shown at all.
class SyncBannerBehavior {
  const SyncBannerBehavior({required this.show, this.autoHide});

  /// Whether the banner is visible for this status.
  final bool show;

  /// How long to keep it visible before hiding it. `null` means "keep it until
  /// the next status change" (used while actively syncing).
  final Duration? autoHide;
}

SyncBannerBehavior syncBannerBehavior(SyncStatus status) {
  switch (status) {
    case SyncStatus.idle:
      return const SyncBannerBehavior(show: false);
    case SyncStatus.syncing:
      return const SyncBannerBehavior(show: true);
    case SyncStatus.synced:
      return const SyncBannerBehavior(
          show: true, autoHide: Duration(seconds: 3));
    case SyncStatus.offline:
    case SyncStatus.error:
      return const SyncBannerBehavior(
          show: true, autoHide: Duration(seconds: 5));
  }
}

/// Whether a new status is worth pushing onto the status stream. Identical
/// consecutive emissions (same status *and* message) are dropped, so routine
/// re-syncs that change nothing don't re-flash the banner.
bool shouldEmitSyncStatus(
        SyncStatus prevStatus, String? prevMessage,
        SyncStatus nextStatus, String? nextMessage) =>
    prevStatus != nextStatus || prevMessage != nextMessage;
