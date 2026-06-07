/// Pure rule used by the HTTP sync to decide whether a round actually
/// succeeded.
///
/// A round counts as successful only when BOTH the pull and the push leg
/// completed. The reachability probe hits an *open* endpoint
/// (`/api/system/readiness`, no clinic token), so it can pass even when the
/// authenticated `/api/sync/export` and `/api/sync/import` calls are rejected
/// (e.g. a stale clinic token → 401). Requiring both legs keeps the sync
/// banner honest — it must not read "Synced" when nothing actually moved.
bool syncRoundSucceeded({required bool pullOk, required bool pushOk}) =>
    pullOk && pushOk;
