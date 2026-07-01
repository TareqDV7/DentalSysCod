import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';
import '../models/marketing_post.dart';
import '../services/post_service.dart';
import '../state/app_state.dart';
import '../utils/app_strings.dart';

/// Read-only viewer for marketing posts created in the Post Studio desktop tab.
///
/// Lists posts fetched from `GET /api/posts` (thumbnail grid).
/// Tapping a post opens a full-screen image view built from
/// `GET /api/posts/<id>/image`, with a share action that hands the rendered
/// PNG bytes to the OS share sheet via `share_plus`.
class PostsScreen extends StatefulWidget {
  const PostsScreen({super.key});

  @override
  State<PostsScreen> createState() => _PostsScreenState();
}

class _PostsScreenState extends State<PostsScreen> {
  List<MarketingPost> _posts = [];
  bool _loading = true;
  String? _error;

  late PostService _service;
  bool _serviceInitialized = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_serviceInitialized) {
      // Build the service from the live API once on first dependency resolution.
      _service = PostService(context.read<AppState>().api);
      _serviceInitialized = true;
      _load();
    }
  }

  Future<void> _load({bool silent = false}) async {
    if (!mounted) return;
    if (!silent) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }
    try {
      final posts = await _service.listPosts();
      if (mounted) {
        setState(() {
          _posts = posts;
          _loading = false;
        });
      }
    } on Exception catch (e) {
      if (mounted) {
        setState(() {
          _loading = false;
          _error = e.toString();
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final ar = context.watch<AppState>().isArabic;
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: () => _load(silent: true),
        child: Builder(
          builder: (_) {
            if (_loading) {
              return const Center(child: CircularProgressIndicator());
            }
            if (_error != null) {
              return Center(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.error_outline, size: 48, color: scheme.error),
                      const SizedBox(height: 12),
                      Text(
                        AppStrings.t('failed_to_load_data', isArabic: ar),
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 16),
                      FilledButton(
                        onPressed: _load,
                        child: Text(AppStrings.t('retry', isArabic: ar)),
                      ),
                    ],
                  ),
                ),
              );
            }
            if (_posts.isEmpty) {
              return Center(
                child: Padding(
                  padding: const EdgeInsets.all(32),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        Icons.photo_library_outlined,
                        size: 56,
                        color: scheme.onSurfaceVariant.withAlpha(128),
                      ),
                      const SizedBox(height: 16),
                      Text(
                        AppStrings.t('no_posts', isArabic: ar),
                        style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                          color: scheme.onSurfaceVariant,
                        ),
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ),
                ),
              );
            }
            return GridView.builder(
              padding: const EdgeInsets.all(12),
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 2,
                mainAxisSpacing: 10,
                crossAxisSpacing: 10,
                childAspectRatio: 0.85,
              ),
              itemCount: _posts.length,
              itemBuilder: (ctx, i) =>
                  _PostTile(post: _posts[i], service: _service, isArabic: ar),
            );
          },
        ),
      ),
    );
  }
}

// ─── Post list tile ──────────────────────────────────────────────────────────

class _PostTile extends StatelessWidget {
  const _PostTile({
    required this.post,
    required this.service,
    required this.isArabic,
  });

  final MarketingPost post;
  final PostService service;
  final bool isArabic;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => Navigator.push(
          context,
          MaterialPageRoute<void>(
            builder: (_) => _PostDetailScreen(
              post: post,
              service: service,
              isArabic: isArabic,
            ),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Expanded(
              child: _PostThumbnail(postId: post.id, service: service),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    post.theme,
                    style: Theme.of(context).textTheme.labelMedium?.copyWith(
                      fontWeight: FontWeight.w600,
                      color: scheme.primary,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  if (post.createdAt != null && post.createdAt!.isNotEmpty)
                    Text(
                      post.createdAt!.length >= 10
                          ? post.createdAt!.substring(0, 10)
                          : post.createdAt!,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: scheme.onSurfaceVariant,
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ─── Thumbnail widget (lazy fetch) ───────────────────────────────────────────

class _PostThumbnail extends StatefulWidget {
  const _PostThumbnail({required this.postId, required this.service});

  final int postId;
  final PostService service;

  @override
  State<_PostThumbnail> createState() => _PostThumbnailState();
}

class _PostThumbnailState extends State<_PostThumbnail> {
  List<int>? _bytes;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _fetch();
  }

  Future<void> _fetch() async {
    try {
      final bytes = await widget.service.fetchImageBytes(widget.postId);
      if (mounted) {
        setState(() {
          _bytes = bytes;
          _loading = false;
        });
      }
    } on Exception {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Center(
        child: SizedBox(
          width: 24,
          height: 24,
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
      );
    }
    final bytes = _bytes;
    if (bytes == null || bytes.isEmpty) {
      return const Center(
        child: Icon(Icons.broken_image_outlined, color: Colors.grey),
      );
    }
    return Image.memory(
      Uint8List.fromList(bytes),
      fit: BoxFit.cover,
      gaplessPlayback: true,
    );
  }
}

// ─── Full-screen detail view ──────────────────────────────────────────────────

class _PostDetailScreen extends StatefulWidget {
  const _PostDetailScreen({
    required this.post,
    required this.service,
    required this.isArabic,
  });

  final MarketingPost post;
  final PostService service;
  final bool isArabic;

  @override
  State<_PostDetailScreen> createState() => _PostDetailScreenState();
}

class _PostDetailScreenState extends State<_PostDetailScreen> {
  List<int>? _bytes;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _fetchFull();
  }

  Future<void> _fetchFull() async {
    try {
      final bytes = await widget.service.fetchImageBytes(widget.post.id);
      if (mounted) {
        setState(() {
          _bytes = bytes;
          _loading = false;
        });
      }
    } on Exception catch (e) {
      if (mounted) {
        setState(() {
          _loading = false;
          _error = e.toString();
        });
      }
    }
  }

  /// Hands the rendered PNG bytes to the OS share sheet. [btnContext] is the
  /// share button's own context so the iPad popover anchors to it.
  Future<void> _share(BuildContext btnContext) async {
    final bytes = _bytes;
    if (bytes == null || bytes.isEmpty) return;
    // Capture before the await so we never touch context across the async gap.
    final messenger = ScaffoldMessenger.of(btnContext);
    final box = btnContext.findRenderObject() as RenderBox?;
    final origin = box != null
        ? box.localToGlobal(Offset.zero) & box.size
        : null;
    try {
      await SharePlus.instance.share(
        ShareParams(
          files: [
            XFile.fromData(Uint8List.fromList(bytes), mimeType: 'image/png'),
          ],
          // XFile.fromData ignores its name arg on most platforms; this sets it.
          fileNameOverrides: ['post_${widget.post.id}.png'],
          sharePositionOrigin: origin,
        ),
      );
    } on Exception {
      messenger.showSnackBar(
        SnackBar(
          content: Text(
            AppStrings.t('share_failed', isArabic: widget.isArabic),
          ),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final ar = widget.isArabic;
    final scheme = Theme.of(context).colorScheme;
    final bytes = _bytes;
    return Scaffold(
      appBar: AppBar(
        title: Text(AppStrings.t('nav_posts', isArabic: ar)),
        actions: [
          // Only offer sharing once the full-resolution PNG is in memory.
          if (bytes != null && bytes.isNotEmpty)
            Builder(
              // A child context anchors the iPad share-sheet popover.
              builder: (btnContext) => IconButton(
                icon: const Icon(Icons.share),
                tooltip: AppStrings.t('share', isArabic: ar),
                onPressed: () => _share(btnContext),
              ),
            ),
        ],
      ),
      backgroundColor: Colors.black,
      body: Builder(
        builder: (_) {
          if (_loading) {
            return const Center(
              child: CircularProgressIndicator(color: Colors.white),
            );
          }
          if (_error != null || bytes == null || bytes.isEmpty) {
            return Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(
                    Icons.error_outline,
                    size: 48,
                    color: Colors.white54,
                  ),
                  const SizedBox(height: 12),
                  Text(
                    AppStrings.t('failed_to_load_data', isArabic: ar),
                    style: const TextStyle(color: Colors.white70),
                  ),
                  const SizedBox(height: 16),
                  FilledButton(
                    onPressed: _fetchFull,
                    child: Text(AppStrings.t('retry', isArabic: ar)),
                  ),
                ],
              ),
            );
          }
          return InteractiveViewer(
            minScale: 0.5,
            maxScale: 6.0,
            child: Center(
              child: Image.memory(
                Uint8List.fromList(bytes),
                fit: BoxFit.contain,
              ),
            ),
          );
        },
      ),
      bottomNavigationBar: bytes != null && bytes.isNotEmpty
          ? SafeArea(
              child: Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 8,
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${AppStrings.t('post_theme_label', isArabic: ar)}${widget.post.theme}',
                      style: TextStyle(color: scheme.onSurface.withAlpha(200)),
                    ),
                    if (widget.post.doctorName.isNotEmpty)
                      Text(
                        '${AppStrings.t('post_doctor_label', isArabic: ar)}${widget.post.doctorName}',
                        style: TextStyle(
                          color: scheme.onSurface.withAlpha(200),
                        ),
                      ),
                    if (widget.post.createdAt != null &&
                        widget.post.createdAt!.isNotEmpty)
                      Text(
                        '${AppStrings.t('date', isArabic: ar)}: '
                        '${widget.post.createdAt!.length >= 10 ? widget.post.createdAt!.substring(0, 10) : widget.post.createdAt!}',
                        style: TextStyle(
                          color: scheme.onSurface.withAlpha(150),
                        ),
                      ),
                  ],
                ),
              ),
            )
          : null,
    );
  }
}
