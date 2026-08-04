/// Native audio storage: files, exactly as phase 1 had them.
///
/// This half is deliberately boring. The web half is where the work is, and
/// keeping this one identical in behaviour to the pre-existing code is what
/// makes the refactor safe: nothing about capture on a phone changed.
library;

import 'dart:io';
import 'dart:typed_data';

import 'package:path_provider/path_provider.dart';

import 'blob_store.dart';

class FileBlobStore implements BlobStore {
  FileBlobStore({Directory? directory}) : _directory = directory;

  final Directory? _directory;
  Directory? _resolved;

  Future<Directory> _captures() async {
    final cached = _resolved;
    if (cached != null) return cached;
    final base = _directory ?? await getApplicationDocumentsDirectory();
    final captures = Directory('${base.path}/captures');
    if (!captures.existsSync()) captures.createSync(recursive: true);
    return _resolved = captures;
  }

  Future<File> _file(String key, String extension) async =>
      File('${(await _captures()).path}/$key.$extension');

  /// The extension is not stored, so it is recovered by looking. Cheap, and it
  /// keeps the queue entry free of a detail it should not have to carry.
  Future<File?> _find(String key) async {
    final directory = await _captures();
    if (!directory.existsSync()) return null;
    for (final entity in directory.listSync()) {
      if (entity is File) {
        final name = entity.uri.pathSegments.last;
        if (name == key || name.startsWith('$key.')) return entity;
      }
    }
    return null;
  }

  @override
  Future<String?> recordingTarget(String key, String extension) async =>
      (await _file(key, extension)).path;

  @override
  Future<bool> ingest(
    String key,
    String source, {
    required String extension,
  }) async {
    final produced = File(source);
    if (!produced.existsSync()) return false;

    final target = await _file(key, extension);
    // Usually a no-op: the recorder wrote straight to the target, because
    // `recordingTarget` told it to. The rename covers the platforms where the
    // plugin ignores the requested path and picks its own temporary file.
    if (produced.absolute.path != target.absolute.path) {
      try {
        await produced.rename(target.path);
      } on FileSystemException {
        // Across filesystems a rename fails where a copy succeeds.
        await target.writeAsBytes(await produced.readAsBytes(), flush: true);
        try {
          await produced.delete();
        } on FileSystemException {
          // A leftover temporary file costs disk, not correctness.
        }
      }
    }
    return target.existsSync();
  }

  @override
  Future<Uint8List?> read(String key) async {
    final file = await _find(key);
    if (file == null) return null;
    return file.readAsBytes();
  }

  @override
  Future<bool> exists(String key) async => (await _find(key)) != null;

  @override
  Future<int?> size(String key) async {
    final file = await _find(key);
    return file?.lengthSync();
  }

  @override
  Future<void> delete(String key) async {
    final file = await _find(key);
    if (file == null) return;
    try {
      await file.delete();
    } on FileSystemException {
      // Best effort, same reasoning as above.
    }
  }
}

BlobStore createBlobStore() => FileBlobStore();
