/// Parses arithmetic typed into money fields (e.g. "20+20") and decides when
/// the raw expression is worth preserving verbatim — the mobile mirror of the
/// desktop's `sanitize_amount_expr`. No `eval`/mirrors: a tiny recursive-descent
/// evaluator over `+ - * /` and parentheses, decimals only.
class AmountExpr {
  static final RegExp _safe = RegExp(r'^[0-9+\-*/().\s]+$');
  static final RegExp _hasAddMulDiv = RegExp(r'[+*/]');
  static final RegExp _digitMinusDigit = RegExp(r'\d\s*-\s*\d');

  /// The numeric value of [raw], or null when it isn't a valid expression
  /// (empty, too long, illegal chars, malformed, or divide-by-zero). A plain
  /// number returns its own value.
  static double? evaluate(String raw) {
    final s = raw.trim();
    if (s.isEmpty || s.length > 40 || !_safe.hasMatch(s)) {
      return null;
    }
    try {
      final p = _Parser(s);
      final v = p.parseExpression();
      if (!p.atEnd) {
        return null;
      }
      if (v.isNaN || v.isInfinite) {
        return null;
      }
      return v;
    } catch (_) {
      return null;
    }
  }

  /// The cleaned expression string to PERSIST, or null when there's nothing
  /// worth keeping. Mirrors the desktop: keep it only when it actually contains
  /// an operator (a bare number or a lone leading minus has nothing to
  /// preserve) and it evaluates.
  static String? exprIfMeaningful(String raw) {
    final s = raw.trim();
    if (evaluate(s) == null) {
      return null;
    }
    if (!_hasAddMulDiv.hasMatch(s) && !_digitMinusDigit.hasMatch(s)) {
      return null;
    }
    return s;
  }

  /// Convenience for form save handlers: returns the numeric value (0 when
  /// blank/invalid) plus the expression to store (null unless meaningful).
  static ({double value, String? expr}) parse(String raw) {
    final value = evaluate(raw) ?? double.tryParse(raw.trim()) ?? 0;
    return (value: value, expr: exprIfMeaningful(raw));
  }
}

class _Parser {
  final String _s;
  int _i = 0;
  _Parser(this._s);

  bool get atEnd {
    _skip();
    return _i >= _s.length;
  }

  void _skip() {
    while (_i < _s.length && _s[_i] == ' ') {
      _i++;
    }
  }

  double parseExpression() {
    var v = _parseTerm();
    while (true) {
      _skip();
      if (_i >= _s.length) {
        break;
      }
      final c = _s[_i];
      if (c == '+') {
        _i++;
        v += _parseTerm();
      } else if (c == '-') {
        _i++;
        v -= _parseTerm();
      } else {
        break;
      }
    }
    return v;
  }

  double _parseTerm() {
    var v = _parseFactor();
    while (true) {
      _skip();
      if (_i >= _s.length) {
        break;
      }
      final c = _s[_i];
      if (c == '*') {
        _i++;
        v *= _parseFactor();
      } else if (c == '/') {
        _i++;
        final d = _parseFactor();
        v = d == 0 ? double.nan : v / d;
      } else {
        break;
      }
    }
    return v;
  }

  double _parseFactor() {
    _skip();
    if (_i >= _s.length) {
      throw const FormatException('unexpected end of expression');
    }
    final c = _s[_i];
    if (c == '+') {
      _i++;
      return _parseFactor();
    }
    if (c == '-') {
      _i++;
      return -_parseFactor();
    }
    if (c == '(') {
      _i++;
      final v = parseExpression();
      _skip();
      if (_i >= _s.length || _s[_i] != ')') {
        throw const FormatException('missing closing parenthesis');
      }
      _i++;
      return v;
    }
    return _parseNumber();
  }

  double _parseNumber() {
    _skip();
    final start = _i;
    while (_i < _s.length && (_isDigit(_s[_i]) || _s[_i] == '.')) {
      _i++;
    }
    if (_i == start) {
      throw const FormatException('expected a number');
    }
    final n = double.tryParse(_s.substring(start, _i));
    if (n == null) {
      throw const FormatException('malformed number');
    }
    return n;
  }

  bool _isDigit(String c) {
    final u = c.codeUnitAt(0);
    return u >= 48 && u <= 57;
  }
}
