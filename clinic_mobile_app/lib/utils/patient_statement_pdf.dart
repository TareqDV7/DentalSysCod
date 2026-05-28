import 'dart:typed_data';

import 'package:flutter/services.dart' show rootBundle;
import 'package:intl/intl.dart';
import 'package:pdf/pdf.dart';
import 'package:pdf/widgets.dart' as pw;
import 'package:printing/printing.dart';

import '../models/followup.dart';
import '../models/patient.dart';
import 'date_format_helper.dart';

/// Builds the printable per-patient statement, mirroring the desktop's
/// `/api/patients/{id}/invoice-summary` view: one row per follow-up
/// (Date · Description · Price · Discount · Paid · Balance) plus the five
/// totals, keeping the verbatim "20+20 = ₪40" expressions the user typed.
///
/// Offline note: the Arabic-capable font is fetched/cached via PdfGoogleFonts;
/// if that fails (fully offline, never cached) it degrades to the built-in
/// Latin font, so Arabic names may not shape until a statement is generated
/// once with connectivity.
class PatientStatementPdf {
  static final NumberFormat _money = NumberFormat('#,##0.00', 'en');

  static String _amt(double value, String? expr) {
    final v = '₪ ${_money.format(value)}';
    final e = (expr ?? '').trim();
    return e.isEmpty ? v : '$e = $v';
  }

  static String _displayDate(String raw) {
    final dt = DateFormatHelper.parseApiDate(raw) ??
        DateFormatHelper.parseDisplayDate(raw);
    return dt == null ? raw : DateFormatHelper.formatDate(dt);
  }

  /// Statement totals, byte-for-byte with the desktop's invoice-summary:
  /// total_to_pay = max(Σprice − Σdiscount, 0); left = max(to_pay − Σpaid, 0).
  /// Pure so it can be unit-tested independently of the PDF/font/asset stack.
  static ({
    double price,
    double discount,
    double toPay,
    double paid,
    double left,
  }) computeTotals(List<Followup> followups) {
    var price = 0.0, discount = 0.0, paid = 0.0;
    for (final f in followups) {
      price += f.price;
      discount += f.discount;
      paid += f.payment;
    }
    final toPay = (price - discount).clamp(0, double.infinity).toDouble();
    final left = (toPay - paid).clamp(0, double.infinity).toDouble();
    return (price: price, discount: discount, toPay: toPay, paid: paid, left: left);
  }

  /// Generate the statement and hand it to the OS print / share sheet
  /// (layoutPdf shows a preview with both print and share on mobile).
  static Future<void> printOrShare({
    required Patient patient,
    required List<Followup> followups,
    required String Function(String) label,
    required bool isArabic,
  }) async {
    await Printing.layoutPdf(
      name: 'statement_${patient.id ?? patient.fullName}.pdf',
      onLayout: (format) => build(
        patient: patient,
        followups: followups,
        label: label,
        isArabic: isArabic,
        format: format,
      ),
    );
  }

  /// Pure builder — returns the PDF bytes. Totals match the desktop exactly:
  /// total_to_pay = max(Σprice − Σdiscount, 0); left = max(to_pay − Σpaid, 0).
  static Future<Uint8List> build({
    required Patient patient,
    required List<Followup> followups,
    required String Function(String) label,
    required bool isArabic,
    PdfPageFormat format = PdfPageFormat.a4,
  }) async {
    final totals = computeTotals(followups);

    pw.Font? base, bold;
    try {
      base = await PdfGoogleFonts.cairoRegular();
      bold = await PdfGoogleFonts.cairoBold();
    } catch (_) {/* offline & uncached → fall back to built-in Latin font */}

    pw.MemoryImage? logo;
    try {
      final data = await rootBundle.load('assets/icon/dentacare_icon.png');
      logo = pw.MemoryImage(data.buffer.asUint8List());
    } catch (_) {/* logo is decorative — skip if unavailable */}

    final theme = (base != null && bold != null)
        ? pw.ThemeData.withFont(base: base, bold: bold)
        : pw.ThemeData.base();
    final dir = isArabic ? pw.TextDirection.rtl : pw.TextDirection.ltr;
    final clinicName = isArabic
        ? 'عيادة د. وصفي برزق للأسنان'
        : 'Dr. Wasfy Barzaq Dental Clinic';

    final headers = [
      label('date'),
      label('description'),
      label('price'),
      label('discount'),
      label('paid'),
      label('balance'),
    ];

    final rows = followups.map((f) {
      final tooth = (f.toothNo ?? '').trim();
      final desc = tooth.isEmpty
          ? f.treatmentProcedure
          : '${f.treatmentProcedure}  #$tooth';
      final discCell = (f.discount > 0 || (f.discountExpr ?? '').trim().isNotEmpty)
          ? _amt(f.discount, f.discountExpr)
          : '—';
      return [
        _displayDate(f.followupDate),
        desc,
        _amt(f.price, f.priceExpr),
        discCell,
        _amt(f.payment, f.paymentExpr),
        '₪ ${_money.format(f.remainingAmount)}',
      ];
    }).toList();

    final doc = pw.Document();
    doc.addPage(
      pw.MultiPage(
        theme: theme,
        textDirection: dir,
        pageFormat: format,
        build: (context) => [
          pw.Row(
            crossAxisAlignment: pw.CrossAxisAlignment.center,
            children: [
              if (logo != null) ...[
                pw.Image(logo, height: 54, width: 54),
                pw.SizedBox(width: 14),
              ],
              pw.Expanded(
                child: pw.Column(
                  crossAxisAlignment: pw.CrossAxisAlignment.start,
                  children: [
                    pw.Text(label('statement'),
                        style: pw.TextStyle(
                            fontSize: 22, fontWeight: pw.FontWeight.bold)),
                    pw.Text(clinicName,
                        style: const pw.TextStyle(
                            fontSize: 12, color: PdfColors.grey700)),
                  ],
                ),
              ),
            ],
          ),
          pw.SizedBox(height: 14),
          pw.Text('${label('patient')}: ${patient.fullName}',
              style: pw.TextStyle(fontSize: 13, fontWeight: pw.FontWeight.bold)),
          if ((patient.phone ?? '').trim().isNotEmpty)
            pw.Text('${label('phone')}: ${patient.phone}',
                style: const pw.TextStyle(
                    fontSize: 11, color: PdfColors.grey700)),
          pw.SizedBox(height: 12),
          if (rows.isEmpty)
            pw.Text(label('no_data'))
          else
            pw.TableHelper.fromTextArray(
              headers: headers,
              data: rows,
              border: pw.TableBorder.all(color: PdfColors.grey400, width: 0.5),
              headerDecoration:
                  const pw.BoxDecoration(color: PdfColors.grey200),
              headerStyle: pw.TextStyle(
                  fontSize: 10, fontWeight: pw.FontWeight.bold),
              cellStyle: const pw.TextStyle(fontSize: 10),
              cellPadding:
                  const pw.EdgeInsets.symmetric(horizontal: 6, vertical: 5),
              columnWidths: {
                0: const pw.FlexColumnWidth(1.6),
                1: const pw.FlexColumnWidth(3.0),
                2: const pw.FlexColumnWidth(1.6),
                3: const pw.FlexColumnWidth(1.6),
                4: const pw.FlexColumnWidth(1.6),
                5: const pw.FlexColumnWidth(1.6),
              },
            ),
          pw.SizedBox(height: 16),
          pw.Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              _totalCard(label('subtotal'), totals.price),
              _totalCard(label('discount'), totals.discount),
              _totalCard(label('total_to_pay'), totals.toPay, emphasize: true),
              _totalCard(label('paid'), totals.paid),
              _totalCard(label('left'), totals.left, emphasize: true),
            ],
          ),
        ],
      ),
    );
    return doc.save();
  }

  static pw.Widget _totalCard(String label, double value,
      {bool emphasize = false}) {
    return pw.Container(
      padding: const pw.EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: pw.BoxDecoration(
        color: emphasize ? PdfColors.blue50 : PdfColors.grey100,
        borderRadius: pw.BorderRadius.circular(8),
        border: pw.Border.all(color: PdfColors.grey300, width: 0.5),
      ),
      child: pw.Column(
        crossAxisAlignment: pw.CrossAxisAlignment.start,
        children: [
          pw.Text(label,
              style: const pw.TextStyle(fontSize: 9, color: PdfColors.grey700)),
          pw.SizedBox(height: 2),
          pw.Text('₪ ${_money.format(value)}',
              style: pw.TextStyle(
                  fontSize: 13, fontWeight: pw.FontWeight.bold)),
        ],
      ),
    );
  }
}
