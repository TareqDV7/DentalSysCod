/// A saved marketing post from the Post Studio.
///
/// Each row comes from `GET /api/posts` → `{id, theme, size, doctor_name,
/// photo_count, created_at}`.  The image bytes are fetched separately through
/// `GET /api/posts/<id>/image` (PNG), mirroring the medical-image pattern.
class MarketingPost {
  final int id;
  final String theme;
  final String size;
  final String doctorName;
  final int photoCount;
  final String? createdAt;

  const MarketingPost({
    required this.id,
    required this.theme,
    required this.size,
    required this.doctorName,
    required this.photoCount,
    this.createdAt,
  });

  factory MarketingPost.fromJson(Map<String, dynamic> json) => MarketingPost(
    id: (json['id'] as num).toInt(),
    theme: (json['theme'] ?? '').toString(),
    size: (json['size'] ?? '').toString(),
    doctorName: (json['doctor_name'] ?? '').toString(),
    photoCount: json['photo_count'] is num
        ? (json['photo_count'] as num).toInt()
        : int.tryParse('${json['photo_count']}') ?? 0,
    createdAt: json['created_at']?.toString(),
  );

  Map<String, dynamic> toJson() => {
    'id': id,
    'theme': theme,
    'size': size,
    'doctor_name': doctorName,
    'photo_count': photoCount,
    if (createdAt != null) 'created_at': createdAt,
  };
}
