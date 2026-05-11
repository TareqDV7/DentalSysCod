import 'package:intl/intl.dart';

class DateFormatHelper {
  /// Format date for display as DD/MM/YYYY
  static String formatDate(DateTime date) {
    return DateFormat('dd/MM/yyyy').format(date);
  }

  /// Format date and time for display as DD/MM/YYYY HH:MM
  static String formatDateTime(DateTime dateTime) {
    return DateFormat('dd/MM/yyyy HH:mm').format(dateTime);
  }

  /// Format date for API as YYYY-MM-DD
  static String formatDateForApi(DateTime date) {
    return DateFormat('yyyy-MM-dd').format(date);
  }

  /// Format date-time for API as YYYY-MM-DDTHH:MM:SS
  static String formatDateTimeForApi(DateTime dateTime) {
    return DateFormat('yyyy-MM-ddTHH:mm:ss').format(dateTime);
  }

  /// Parse DD/MM/YYYY to DateTime
  static DateTime? parseDisplayDate(String dateStr) {
    try {
      return DateFormat('dd/MM/yyyy').parse(dateStr);
    } catch (e) {
      return null;
    }
  }

  /// Parse YYYY-MM-DD to DateTime
  static DateTime? parseApiDate(String dateStr) {
    try {
      if (dateStr.contains('T')) {
        return DateTime.parse(dateStr);
      }
      return DateFormat('yyyy-MM-dd').parse(dateStr);
    } catch (e) {
      return null;
    }
  }

  /// Get date for week start (Monday) in DD/MM/YYYY format
  static String getWeekStartDisplay(DateTime date) {
    final monday = date.subtract(Duration(days: date.weekday - 1));
    return formatDate(monday);
  }

  /// Get date for week start (Monday) in YYYY-MM-DD format for API
  static String getWeekStartForApi(DateTime date) {
    final monday = date.subtract(Duration(days: date.weekday - 1));
    return formatDateForApi(monday);
  }
}
