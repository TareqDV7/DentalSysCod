import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/utils/pairing_payload.dart';

void main() {
  group('parsePairingPayload', () {
    test('valid https payload parses url and token', () {
      final raw =
          jsonEncode({'v': 1, 'u': 'https://app.dentacare.tech', 't': 'TOK-123'});
      final result = parsePairingPayload(raw);
      expect(result, isNotNull);
      expect(result!.cloudUrl, 'https://app.dentacare.tech');
      expect(result.clinicToken, 'TOK-123');
    });

    test('trims surrounding whitespace in the raw string and fields', () {
      final raw =
          '  ${jsonEncode({'v': 1, 'u': ' https://c.example ', 't': ' tok '})}  ';
      final result = parsePairingPayload(raw);
      expect(result, isNotNull);
      expect(result!.cloudUrl, 'https://c.example');
      expect(result.clinicToken, 'tok');
    });

    test('accepts version as a numeric string', () {
      final raw = jsonEncode({'v': '1', 'u': 'https://c.example', 't': 'tok'});
      expect(parsePairingPayload(raw), isNotNull);
    });

    test('allows http only for localhost / 127.0.0.1', () {
      expect(
        parsePairingPayload(
            jsonEncode({'v': 1, 'u': 'http://localhost:5000', 't': 'tok'})),
        isNotNull,
      );
      expect(
        parsePairingPayload(
            jsonEncode({'v': 1, 'u': 'http://127.0.0.1:5000', 't': 'tok'})),
        isNotNull,
      );
    });

    test('returns null for invalid JSON', () {
      expect(parsePairingPayload('not json'), isNull);
      expect(parsePairingPayload('{oops'), isNull);
      expect(parsePairingPayload(''), isNull);
      expect(parsePairingPayload('   '), isNull);
    });

    test('returns null when JSON is not an object', () {
      expect(parsePairingPayload('[1,2,3]'), isNull);
      expect(parsePairingPayload('"just a string"'), isNull);
      expect(parsePairingPayload('42'), isNull);
    });

    test('returns null for the wrong / missing version', () {
      expect(
        parsePairingPayload(
            jsonEncode({'v': 2, 'u': 'https://c.example', 't': 'tok'})),
        isNull,
      );
      expect(
        parsePairingPayload(jsonEncode({'u': 'https://c.example', 't': 'tok'})),
        isNull,
      );
      expect(
        parsePairingPayload(
            jsonEncode({'v': 'abc', 'u': 'https://c.example', 't': 'tok'})),
        isNull,
      );
    });

    test('returns null when url or token is missing or blank', () {
      expect(
        parsePairingPayload(jsonEncode({'v': 1, 't': 'tok'})),
        isNull,
      );
      expect(
        parsePairingPayload(jsonEncode({'v': 1, 'u': 'https://c.example'})),
        isNull,
      );
      expect(
        parsePairingPayload(jsonEncode({'v': 1, 'u': '   ', 't': 'tok'})),
        isNull,
      );
      expect(
        parsePairingPayload(
            jsonEncode({'v': 1, 'u': 'https://c.example', 't': '   '})),
        isNull,
      );
    });

    test('returns null when url is non-https (and not localhost)', () {
      expect(
        parsePairingPayload(
            jsonEncode({'v': 1, 'u': 'http://example.com', 't': 'tok'})),
        isNull,
      );
      expect(
        parsePairingPayload(
            jsonEncode({'v': 1, 'u': 'ftp://example.com', 't': 'tok'})),
        isNull,
      );
      expect(
        parsePairingPayload(jsonEncode({'v': 1, 'u': 'example.com', 't': 'tok'})),
        isNull,
      );
    });

    test('returns null when url/token fields are not strings', () {
      expect(
        parsePairingPayload(jsonEncode({'v': 1, 'u': 123, 't': 'tok'})),
        isNull,
      );
      expect(
        parsePairingPayload(
            jsonEncode({'v': 1, 'u': 'https://c.example', 't': 99})),
        isNull,
      );
    });
  });
}
