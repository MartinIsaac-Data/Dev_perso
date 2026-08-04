/// Where recorded audio lives until the server has it.
///
/// This port exists because of one fact the phase-1 code assumed away: a
/// capture's bytes are a *file* on Android, iOS, Linux, macOS and Windows, and
/// they are **not** a file in a browser. `dart:io` compiles for the web and
/// throws at run time, so the phase-1 capture path produced a web build that
/// built cleanly and could not record a single note — the one thing the product
/// is for.
///
/// The contract is deliberately small and deliberately opaque. A caller never
/// learns whether it is holding a path, a blob URL or an IndexedDB key: it
/// holds an *audio key*, which is the `client_capture_id` (ADR-009). That
/// identity already exists before the bytes do, so it makes a natural handle on
/// every platform.
///
/// **Durability is the point, not convenience.** `write`/`ingest` must have
/// committed before they return, because the next thing the caller does is
/// persist a queue entry pointing at the key, and a queue entry pointing at
/// bytes that never landed is worse than no queue entry at all.
library;

import 'dart:typed_data';

import 'blob_store_io.dart' if (dart.library.js_interop) 'blob_store_web.dart'
    as impl;

abstract class BlobStore {
  /// Where the recorder should write, if this platform records to a location we
  /// choose. Null means the platform decides — a browser hands back a blob URL
  /// and ignores any path we suggest.
  Future<String?> recordingTarget(String key, String extension);

  /// Take what the recorder produced and store it under [key], durably.
  ///
  /// [source] is whatever `AudioRecorder.stop()` returned: a filesystem path on
  /// native, a `blob:` URL in a browser. Returns false when there was nothing
  /// to take, which is a real case on a permission that was revoked mid-record.
  Future<bool> ingest(String key, String source, {required String extension});

  Future<Uint8List?> read(String key);

  Future<bool> exists(String key);

  /// Byte count, or null when the blob is gone. Sent as `audio_bytes` at
  /// declaration, so a wrong answer is better left absent than guessed.
  Future<int?> size(String key);

  Future<void> delete(String key);
}

/// The implementation for the platform this build targets.
BlobStore createBlobStore() => impl.createBlobStore();
