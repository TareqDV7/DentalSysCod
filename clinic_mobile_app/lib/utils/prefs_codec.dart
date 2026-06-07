import 'package:flutter/material.dart' show ThemeMode;

/// Pure string ⇄ value codecs for persisted UI preferences (theme + language).
///
/// Kept separate from storage so the stored representation is stable and unit
/// testable without touching `flutter_secure_storage` (a platform channel).

String encodeThemeMode(ThemeMode mode) {
  switch (mode) {
    case ThemeMode.dark:
      return 'dark';
    case ThemeMode.light:
      return 'light';
    case ThemeMode.system:
      return 'system';
  }
}

/// Decodes a stored theme string. Unknown / null falls back to light — the
/// app's historical default — so a corrupt value never throws.
ThemeMode decodeThemeMode(String? value) {
  switch (value) {
    case 'dark':
      return ThemeMode.dark;
    case 'system':
      return ThemeMode.system;
    case 'light':
      return ThemeMode.light;
    default:
      return ThemeMode.light;
  }
}

/// Only `en` and `ar` are supported; anything else falls back to English.
String decodeLocale(String? value) => value == 'ar' ? 'ar' : 'en';
