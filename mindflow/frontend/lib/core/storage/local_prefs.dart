/// Tiny key–value store on disk.
///
/// One JSON document rather than `shared_preferences`, for the same reason the
/// pending capture queue is one: the app stores a handful of scalars, and a
/// platform-channel dependency for that is a dependency to maintain forever in
/// exchange for nothing measurable. It goes through `DocumentStore`, so it is a
/// file on a device and a `localStorage` entry in a browser (ADR-061).
library;

import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'document_store.dart';

const _documentName = 'prefs.json';

class LocalPrefs {
  LocalPrefs({DocumentStore? documents})
      : _documents = documents ?? createDocumentStore();

  final DocumentStore _documents;
  Map<String, dynamic>? _cache;

  Future<Map<String, dynamic>> _load() async {
    final cached = _cache;
    if (cached != null) return cached;

    final raw = await _documents.read(_documentName);
    if (raw == null || raw.isEmpty) return _cache = <String, dynamic>{};
    try {
      final decoded = jsonDecode(raw);
      return _cache =
          decoded is Map<String, dynamic> ? decoded : <String, dynamic>{};
    } on FormatException {
      // A truncated write must not brick the app; the values here are all
      // regenerable.
      await _documents.delete(_documentName);
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

  Future<void> _flush(Map<String, dynamic> data) =>
      _documents.write(_documentName, jsonEncode(data));
}

final localPrefsProvider = Provider<LocalPrefs>((ref) => LocalPrefs());
