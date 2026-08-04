/// In-memory stand-ins for the two storage ports.
///
/// They exist so the capture tests assert behaviour that is true on every
/// target. Running the queue against a temporary directory tested the four
/// platforms that have a filesystem and said nothing about the two that do not
/// — which is how a web build shipped that could not record a note.
library;

import 'dart:typed_data';

import 'package:mindflow/core/storage/blob_store.dart';
import 'package:mindflow/core/storage/document_store.dart';

class FakeDocumentStore implements DocumentStore {
  final Map<String, String> contents = {};

  @override
  Future<String?> read(String name) async => contents[name];

  @override
  Future<void> write(String name, String value) async => contents[name] = value;

  @override
  Future<void> delete(String name) async => contents.remove(name);
}

class FakeBlobStore implements BlobStore {
  final Map<String, Uint8List> blobs = {};

  /// What `recordingTarget` hands back. Null models a browser, which chooses
  /// its own destination; a string models a device.
  String? Function(String key, String extension)? target;

  /// Sources `ingest` should refuse, modelling a recording the platform lost.
  final Set<String> unreadable = {};

  @override
  Future<String?> recordingTarget(String key, String extension) async =>
      target?.call(key, extension) ?? '/tmp/$key.$extension';

  @override
  Future<bool> ingest(
    String key,
    String source, {
    required String extension,
  }) async {
    if (unreadable.contains(source)) return false;
    blobs[key] = Uint8List.fromList([1, 2, 3, 4]);
    return true;
  }

  @override
  Future<Uint8List?> read(String key) async => blobs[key];

  @override
  Future<bool> exists(String key) async => blobs.containsKey(key);

  @override
  Future<int?> size(String key) async => blobs[key]?.lengthInBytes;

  @override
  Future<void> delete(String key) async => blobs.remove(key);
}
