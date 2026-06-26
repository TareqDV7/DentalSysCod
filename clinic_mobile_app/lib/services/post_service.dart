import '../models/marketing_post.dart';
import 'clinic_api.dart';

/// Fetches marketing posts from the local DentaCare server.
///
/// Read-only: lists posts and fetches image bytes.  No create/edit/delete.
/// Mirrors the HTTP + fetch pattern of [MedicalImageService].
class PostService {
  final ClinicApi _api;

  const PostService(this._api);

  static const _listEndpoint = '/api/posts';

  /// Returns the list of saved posts ordered newest-first.
  Future<List<MarketingPost>> listPosts() async {
    final raw = await _api.getList(_listEndpoint);
    final posts = <MarketingPost>[];
    for (final item in raw) {
      if (item is Map) {
        try {
          posts.add(MarketingPost.fromJson(Map<String, dynamic>.from(item)));
        } on Object {
          // skip malformed row; log nothing to avoid PII leaks
        }
      }
    }
    return posts;
  }

  /// Fetches the PNG bytes for a single post by its server [id].
  Future<List<int>> fetchImageBytes(int id) =>
      _api.getBytes('$_listEndpoint/$id/image');
}
