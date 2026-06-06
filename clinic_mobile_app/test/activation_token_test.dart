import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/utils/activation_token.dart';

/// Mint a key shaped like the vendor signer's output: unpadded base64url
/// payload + '.' + signature.
String _mintKey(Map<String, dynamic> payload, {String sig = 'fakesignature'}) {
  final b64 = base64Url.encode(utf8.encode(jsonEncode(payload)));
  return '${b64.replaceAll('=', '')}.$sig';
}

void main() {
  group('ActivationToken.tryParse', () {
    test('extracts and upper-cases the serial, plus the clinic name', () {
      final key = _mintKey(
          {'serial': 'dental-abcd-1234', 'clinic_name': 'Acme Dental'});
      final tok = ActivationToken.tryParse(key);
      expect(tok, isNotNull);
      expect(tok!.serial, 'DENTAL-ABCD-1234');
      expect(tok.clinicName, 'Acme Dental');
    });

    test('clinic name is null when absent', () {
      final tok = ActivationToken.tryParse(_mintKey({'serial': 'DENTAL-NOCN-1'}));
      expect(tok?.serial, 'DENTAL-NOCN-1');
      expect(tok?.clinicName, isNull);
    });

    test('tolerates surrounding whitespace', () {
      final key = '  ${_mintKey({'serial': 'DENTAL-WS-0001'})}  ';
      expect(ActivationToken.tryParse(key)?.serial, 'DENTAL-WS-0001');
    });

    test('returns null without a signature separator', () {
      expect(ActivationToken.tryParse('not-a-token'), isNull);
    });

    test('returns null on a too-short serial', () {
      expect(ActivationToken.tryParse(_mintKey({'serial': 'SHORT'})), isNull);
    });

    test('returns null on an undecodable payload', () {
      expect(ActivationToken.tryParse('!!!!.sig'), isNull);
    });

    test('returns null when the payload is not a JSON object', () {
      final b64 = base64Url.encode(utf8.encode('"plain string"'));
      expect(ActivationToken.tryParse('${b64.replaceAll('=', '')}.sig'), isNull);
    });
  });
}
