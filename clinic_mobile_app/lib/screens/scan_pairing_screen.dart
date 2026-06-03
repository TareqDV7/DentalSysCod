import 'dart:async';

import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import 'package:provider/provider.dart';

import '../services/api_client.dart' show ApiException;
import '../state/app_state.dart';
import '../utils/pairing_payload.dart';

/// Camera screen that scans the desktop pairing QR and links this device to the
/// clinic by token (no manual URL/serial entry). Manual cloud pairing stays as a
/// fallback in Settings.
class ScanPairingScreen extends StatefulWidget {
  const ScanPairingScreen({super.key});

  @override
  State<ScanPairingScreen> createState() => _ScanPairingScreenState();
}

class _ScanPairingScreenState extends State<ScanPairingScreen> {
  final MobileScannerController _controller = MobileScannerController(
    detectionSpeed: DetectionSpeed.noDuplicates,
    formats: const [BarcodeFormat.qrCode],
  );

  // Guards against re-entrant handling: a single frame can yield several
  // barcodes and the detector keeps firing while we await the link.
  bool _handled = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _onDetect(BarcodeCapture capture) async {
    if (_handled) return;
    final raw = capture.barcodes
        .map((b) => b.rawValue)
        .firstWhere((v) => v != null && v.trim().isNotEmpty, orElse: () => null);
    if (raw == null) return;

    final payload = parsePairingPayload(raw);
    if (payload == null) {
      // Keep scanning — an unrelated QR shouldn't end the session. Surface a
      // brief hint so the user knows it wasn't a clinic pairing code.
      _flash(_isArabic
          ? 'هذا ليس رمز ربط عيادة صالحًا.'
          : 'That is not a valid clinic pairing code.');
      return;
    }

    _handled = true;
    await _controller.stop();
    await _link(payload);
  }

  Future<void> _link(PairingPayload payload) async {
    final app = context.read<AppState>();
    final messenger = ScaffoldMessenger.of(context);
    final navigator = Navigator.of(context);
    final isArabic = _isArabic;
    try {
      await app.linkWithToken(
        cloudUrl: payload.cloudUrl,
        clinicToken: payload.clinicToken,
      );
      messenger.showSnackBar(SnackBar(
        backgroundColor: const Color(0xFF1F9A5F),
        content: Text(isArabic
            ? 'تم ربط الجهاز بالعيادة.'
            : 'Linked to the clinic.'),
      ));
      if (mounted) navigator.pop(true);
    } on ApiException catch (e) {
      _failAndResume(isArabic
          ? 'فشل الربط: ${e.message}'
          : 'Linking failed: ${e.message}');
    } catch (e) {
      _failAndResume(isArabic ? 'فشل الربط: $e' : 'Linking failed: $e');
    }
  }

  void _failAndResume(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      backgroundColor: const Color(0xFFD9434E),
      content: Text(message),
    ));
    // Allow another attempt instead of trapping the user on a dead camera.
    _handled = false;
    unawaited(_controller.start());
  }

  void _flash(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(
        duration: const Duration(seconds: 2),
        content: Text(message),
      ));
  }

  bool get _isArabic => context.read<AppState>().isArabic;

  @override
  Widget build(BuildContext context) {
    final isArabic = context.select<AppState, bool>((s) => s.isArabic);
    return Scaffold(
      appBar: AppBar(
        title: Text(isArabic ? 'مسح رمز الربط' : 'Scan pairing QR'),
        actions: [
          IconButton(
            tooltip: isArabic ? 'الفلاش' : 'Torch',
            icon: const Icon(Icons.flash_on),
            onPressed: () => _controller.toggleTorch(),
          ),
          IconButton(
            tooltip: isArabic ? 'تبديل الكاميرا' : 'Switch camera',
            icon: const Icon(Icons.cameraswitch),
            onPressed: () => _controller.switchCamera(),
          ),
        ],
      ),
      body: Stack(
        children: [
          MobileScanner(
            controller: _controller,
            onDetect: _onDetect,
            errorBuilder: (context, error, child) => _CameraError(
              message: isArabic
                  ? 'تعذّر تشغيل الكاميرا. تحقق من إذن الكاميرا.'
                  : 'Could not start the camera. Check the camera permission.',
            ),
          ),
          // Simple framing guide + instruction overlay.
          IgnorePointer(
            child: Center(
              child: Container(
                width: 240,
                height: 240,
                decoration: BoxDecoration(
                  border: Border.all(color: Colors.white, width: 3),
                  borderRadius: BorderRadius.circular(16),
                ),
              ),
            ),
          ),
          Positioned(
            left: 0,
            right: 0,
            bottom: 32,
            child: Center(
              child: Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                decoration: BoxDecoration(
                  color: Colors.black54,
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  isArabic
                      ? 'وجّه الكاميرا نحو رمز QR على شاشة العيادة'
                      : 'Point the camera at the QR on the clinic screen',
                  style: const TextStyle(color: Colors.white),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _CameraError extends StatelessWidget {
  const _CameraError({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      color: Colors.black,
      alignment: Alignment.center,
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.no_photography_outlined,
              color: Colors.white70, size: 48),
          const SizedBox(height: 12),
          Text(
            message,
            textAlign: TextAlign.center,
            style: const TextStyle(color: Colors.white70),
          ),
        ],
      ),
    );
  }
}
