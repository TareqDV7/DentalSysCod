import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../state/app_state.dart';
import '../utils/app_strings.dart';

class StatusBadge extends StatelessWidget {
  final String status;

  const StatusBadge(this.status, {super.key});

  @override
  Widget build(BuildContext context) {
    final isArabic = context.watch<AppState>().isArabic;
    final (bg, fg, key) = _resolve(status);
    // Unknown statuses fall back to the raw value rather than a catalog key.
    final label = key == null ? status : AppStrings.t(key, isArabic: isArabic);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: bg.withAlpha(30),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: bg.withAlpha(80)),
      ),
      child: Text(label,
          style: TextStyle(
              color: fg,
              fontSize: 11,
              fontWeight: FontWeight.w700,
              letterSpacing: 0.2)),
    );
  }

  (Color, Color, String?) _resolve(String s) {
    switch (s.toLowerCase()) {
      case 'completed':
        return (const Color(0xFF1F9A5F), const Color(0xFF1F9A5F), 'status_completed');
      case 'paid':
        return (const Color(0xFF1F9A5F), const Color(0xFF1F9A5F), 'status_paid');
      case 'scheduled':
        return (const Color(0xFF1D7FB7), const Color(0xFF1D7FB7), 'status_scheduled');
      case 'partial':
        return (const Color(0xFF1D7FB7), const Color(0xFF1D7FB7), 'status_partial');
      case 'postponed':
        return (const Color(0xFFD89E1F), const Color(0xFFD89E1F), 'status_postponed');
      case 'unpaid':
        return (const Color(0xFFD89E1F), const Color(0xFFD89E1F), 'status_unpaid');
      case 'cancelled':
        return (const Color(0xFFD9434E), const Color(0xFFD9434E), 'status_cancelled');
      case 'pending':
        return (const Color(0xFFD9434E), const Color(0xFFD9434E), 'status_pending');
      default:
        return (Colors.grey, Colors.grey, null);
    }
  }
}
