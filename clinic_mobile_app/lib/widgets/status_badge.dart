import 'package:flutter/material.dart';

class StatusBadge extends StatelessWidget {
  final String status;

  const StatusBadge(this.status, {super.key});

  @override
  Widget build(BuildContext context) {
    final (bg, fg, label) = _resolve(status);
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

  (Color, Color, String) _resolve(String s) {
    switch (s.toLowerCase()) {
      case 'completed':
      case 'paid':
        return (const Color(0xFF1F9A5F), const Color(0xFF1F9A5F),
            s == 'paid' ? 'Paid' : 'Completed');
      case 'scheduled':
      case 'partial':
        return (const Color(0xFF1D7FB7), const Color(0xFF1D7FB7),
            s == 'partial' ? 'Partial' : 'Scheduled');
      case 'postponed':
      case 'unpaid':
        return (const Color(0xFFD89E1F), const Color(0xFFD89E1F),
            s == 'unpaid' ? 'Unpaid' : 'Postponed');
      case 'cancelled':
      case 'pending':
        return (const Color(0xFFD9434E), const Color(0xFFD9434E),
            s == 'cancelled' ? 'Cancelled' : 'Pending');
      default:
        return (Colors.grey, Colors.grey, s);
    }
  }
}
