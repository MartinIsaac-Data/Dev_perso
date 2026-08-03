/// Tiny key–value store on disk.
///
/// A JSON file rather than `shared_preferences`, for the same reason the pending
/// capture queue is a JSON file: the app stores a handful of scalars, and a
/// platform-channel dependency for that is a dependency to maintain forever in
/// exchange for nothing measurable.
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path_provider/path_provider.dart';

class LocalPrefs {
  LocalPrefs({Directory? directory}) : _directory = directory;

  final Directory? _directory;
  File? _file;
  Map<String, dynamic>? _cache;

  Future<File> _open() async {
    final existing = _file;
    if (existing != null) return existing;
    final directory = _directory ?? await getApplicationDocumentsDirectory();
    final file = File('${directory.path}/prefs.json');
    _file = file;
    return file;
  }

  Future<Map<String, dynamic>> _load() async {
    final cached = _cache;
    if (cached != null) return cached;

    final file = await _open();
    if (!file.existsSync()) return _cache = <String, dynamic>{};
    try {
      final decoded = jsonDecode(await file.readAsString());
      return _cache =
          decoded is Map<String, dynamic> ? decoded : <String, dynamic>{};
    } on FormatException {
      // A truncated write must not brick the app; the values here are all
      // regenerable.
      await file.delete();
      return _cache = <String, dynamic>{};
    }
  }

  Future<String?> getString(String key) async =>
      (await _load())[key] as String?;

  Future<bool> getBool(String key, {bool fallback = false}) async =>
      (await _load())[key] as bool? ?? fallback;

  Future<void> setString(String key, String value) async {
    final data = await _load();
    data[key] = value;
    await _flush(data);
  }

  Future<void> setBool(String key, {required bool value}) async {
    final data = await _load();
    data[key] = value;
    await _flush(data);
  }

  Future<void> _flush(Map<String, dynamic> data) async {
    final file = await _open();
    await file.writeAsString(jsonEncode(data), flush: true);
  }
}

final localPrefsProvider = Provider<LocalPrefs>((ref) => LocalPrefs());
