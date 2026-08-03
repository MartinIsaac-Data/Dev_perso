/// The device's IANA time zone.
///
/// Every capture carries it, because the backend resolves "jeudi" or "fin de
/// mois" against the zone the words were spoken in, not the server's (ADR-020).
/// Sending an abbreviation such as "CEST" would be useless: it maps to several
/// zones and says nothing about the DST rules that apply next month.
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_timezone/flutter_timezone.dart';

/// Used when the platform cannot answer. A wrong zone shifts due dates by a few
/// hours; refusing to record because of it would be far worse.
const kFallbackTimezone = 'Europe/Paris';

class DeviceTimezone {
  DeviceTimezone({Future<String> Function()? resolve})
      : _resolve = resolve ?? FlutterTimezone.getLocalTimezone;

  final Future<String> Function() _resolve;
  String _cached = kFallbackTimezone;

  /// Last known value, safe to read synchronously on the recording path.
  String get current => _cached;

  Future<String> refresh() async {
    try {
      final name = await _resolve();
      if (name.isNotEmpty) _cached = name;
    } catch (_) {
      // Platform channel unavailable (tests, unsupported platform).
    }
    return _cached;
  }
}

final deviceTimezoneProvider =
    Provider<DeviceTimezone>((ref) => DeviceTimezone());
