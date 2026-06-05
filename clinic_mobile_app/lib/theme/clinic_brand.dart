import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class ClinicBrand {
  // Brand identity — kept as the accent in both light and dark so the UI
  // stays consistent with the DentaCare teal logo / launcher icon.
  static const Color brand = Color(0xFF0F6D7B);
  static const Color brand2 = Color(0xFF1D7FB7);
  static const Color accent = Color(0xFF13B5A7);

  // Light mode tokens
  static const Color bg1 = Color(0xFFF1F7F8);
  static const Color bg2 = Color(0xFFE7F0FF);
  static const Color text = Color(0xFF11243A);
  static const Color muted = Color(0xFF627386);
  static const Color panel = Colors.white;
  static const Color line = Color(0xFFDBE4EF);

  // Dark mode tokens — "Midnight Oceanic" deep navy surfaces.
  static const Color darkBg = Color(0xFF0B1120);
  static const Color darkSurface = Color(0xFF151E2E);
  static const Color darkLine = Color(0xFF24314A);
  static const Color darkText = Color(0xFFE8F1F8);
  static const Color darkMuted = Color(0xFF8BA5BB);

  /// Builds the app theme.
  ///
  /// [arabic] selects a harmonised Arabic typeface (Cairo) for the whole
  /// text theme; Latin uses Plus Jakarta Sans for body and Space Grotesk for
  /// the large numeric/headline scale.
  static ThemeData buildTheme({bool dark = false, bool arabic = false}) {
    final colorScheme = dark
        ? ColorScheme.dark(
            primary: brand,
            secondary: brand2,
            tertiary: accent,
            surface: darkSurface,
            onSurface: darkText,
            onSurfaceVariant: darkMuted,
            outline: darkLine,
            outlineVariant: darkLine,
            error: const Color(0xFFD9434E),
          )
        : ColorScheme.light(
            primary: brand,
            secondary: brand2,
            tertiary: accent,
            surface: panel,
            onSurface: text,
            onSurfaceVariant: muted,
            outline: line,
            outlineVariant: line,
            error: const Color(0xFFD9434E),
          );

    final onColor = dark ? darkText : text;

    // Display/headline font: Cairo for Arabic (Space Grotesk has no Arabic
    // glyphs), Space Grotesk otherwise for a precise "data terminal" feel.
    TextStyle headline({double? fontSize, FontWeight weight = FontWeight.w700}) {
      final style = TextStyle(
        fontWeight: weight,
        color: onColor,
        fontSize: fontSize,
        letterSpacing: -0.4,
      );
      return arabic
          ? GoogleFonts.cairo(textStyle: style)
          : GoogleFonts.spaceGrotesk(textStyle: style);
    }

    final baseTextTheme = arabic
        ? GoogleFonts.cairoTextTheme()
        : GoogleFonts.plusJakartaSansTextTheme();

    final textTheme = baseTextTheme.copyWith(
      headlineLarge: headline(weight: FontWeight.w800),
      headlineMedium: headline(weight: FontWeight.w800),
      headlineSmall: headline(weight: FontWeight.w700),
      titleLarge: headline(weight: FontWeight.w700),
      titleMedium: headline(weight: FontWeight.w700),
      // Small, muted, tracked label — used (uppercased) for stat/field labels.
      labelSmall: TextStyle(
        fontSize: 11,
        fontWeight: FontWeight.w600,
        letterSpacing: 0.8,
        color: dark ? darkMuted : muted,
      ),
    );

    return ThemeData(
      colorScheme: colorScheme,
      useMaterial3: true,
      scaffoldBackgroundColor: dark ? darkBg : bg1,
      textTheme: textTheme.apply(
        bodyColor: onColor,
        displayColor: onColor,
      ),
      appBarTheme: AppBarTheme(
        backgroundColor: Colors.transparent,
        foregroundColor: onColor,
        elevation: 0,
        centerTitle: false,
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: dark ? darkSurface : panel,
        indicatorColor: brand.withAlpha(38),
        labelTextStyle: WidgetStateProperty.all(
          TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w600,
              color: dark ? darkMuted : muted),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: dark ? darkSurface : Colors.white,
        labelStyle: TextStyle(color: dark ? darkMuted : muted),
        hintStyle: TextStyle(color: dark ? darkMuted : muted),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: BorderSide(color: dark ? darkLine : line),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: BorderSide(color: dark ? darkLine : line),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: brand, width: 1.5),
        ),
      ),
      cardTheme: CardThemeData(
        color: dark ? darkSurface : panel,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
          side: BorderSide(color: dark ? darkLine : line),
        ),
        margin: EdgeInsets.zero,
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: brand,
          foregroundColor: Colors.white,
          padding:
              const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
          shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(16)),
          textStyle: const TextStyle(
              fontWeight: FontWeight.w800, fontSize: 15),
        ),
      ),
      dividerTheme: DividerThemeData(
        color: dark ? darkLine : line,
        thickness: 1,
      ),
    );
  }
}
