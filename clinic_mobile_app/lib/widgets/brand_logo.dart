import 'package:flutter/material.dart';

/// The DentaCare logo mark, rendered from the bundled app icon with rounded
/// corners. Used both "inside" (the app-bar header) and "outside" (the
/// activation / unlicensed entry screen) so the brand reads consistently
/// everywhere instead of a generic Material hospital glyph.
class BrandLogo extends StatelessWidget {
  const BrandLogo({super.key, this.size = 34, this.radius = 10});

  final double size;
  final double radius;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(radius),
      child: Image.asset(
        'assets/icon/dentacare_icon.png',
        width: size,
        height: size,
        fit: BoxFit.cover,
        filterQuality: FilterQuality.medium,
      ),
    );
  }
}
