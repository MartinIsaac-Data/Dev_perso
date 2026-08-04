/// Browser audio storage: IndexedDB.
///
/// **Why not `localStorage`.** It is synchronous, capped around five megabytes
/// per origin, and holds strings — so audio would have to be base64, costing a
/// third more. A ten-minute capture at 32 kbps is roughly 2.4 MB, 3.2 MB
/// encoded: one capture would nearly fill the quota and the second would throw.
/// A queue that holds one item is not a queue.
///
/// **Why not just keep the blob URL.** `AudioRecorder.stop()` hands back a
/// `blob:` URL, which is tempting and wrong: the object it names dies with the
/// document. A reload, a crashed tab, or a phone that backgrounded Safari long
/// enough — and the offline queue would point at nothing. Copying the bytes out
/// while the URL is still alive is the entire job of this file, and it is why
/// `ingest` fetches and awaits before returning.
///
/// The store is one object store keyed by `client_capture_id` (ADR-009), which
/// exists before the bytes do.
library;

import 'dart:async';
import 'dart:js_interop';
import 'dart:typed_data';

import 'package:web/web.dart' as web;

import 'blob_store.dart';

const _databaseName = 'mindflow';
const _storeName = 'captures';
const _databaseVersion = 1;

class IndexedDbBlobStore implements BlobStore {
  Future<web.IDBDatabase>? _opening;

  Future<web.IDBDatabase> _database() => _opening ??= _open();

  Future<web.IDBDatabase> _open() {
    final completer = Completer<web.IDBDatabase>();
    final request = web.window.indexedDB.open(_databaseName, _databaseVersion);

    request.onupgradeneeded = (web.Event _) {
      final database = request.result as web.IDBDatabase;
      if (!database.objectStoreNames.contains(_storeName)) {
        database.createObjectStore(_storeName);
      }
    }.toJS;
    request.onsuccess = (web.Event _) {
      completer.complete(request.result as web.IDBDatabase);
    }.toJS;
    request.onerror = (web.Event _) {
      completer.completeError(
        StateError('IndexedDB indisponible : ${request.error?.message}'),
      );
    }.toJS;

    return completer.future;
  }

  Future<T> _await<T extends JSAny?>(web.IDBRequest request) {
    final completer = Completer<T>();
    request.onsuccess = (web.Event _) {
      completer.complete(request.result as T);
    }.toJS;
    request.onerror = (web.Event _) {
      completer.completeError(
        StateError('IndexedDB : ${request.error?.message}'),
      );
    }.toJS;
    return completer.future;
  }

  Future<web.IDBObjectStore> _store({required bool write}) async {
    final database = await _database();
    final transaction = database.transaction(
      _storeName.toJS,
      write ? 'readwrite' : 'readonly',
    );
    return transaction.objectStore(_storeName);
  }

  /// A browser records where it likes and hands back a `blob:` URL, so there is
  /// no target to propose. Returning null says that plainly rather than
  /// inventing a path the plugin would ignore.
  @override
  Future<String?> recordingTarget(String key, String extension) async => null;

  @override
  Future<bool> ingest(
    String key,
    String source, {
    required String extension,
  }) async {
    final bytes = await _fetchBlob(source);
    if (bytes == null || bytes.isEmpty) return false;

    final store = await _store(write: true);
    await _await<JSAny?>(store.put(bytes.toJS, key.toJS));

    // The object URL holds the recording in memory for as long as the document
    // lives. The bytes are safe in IndexedDB now, so hand it back.
    if (source.startsWith('blob:')) {
      web.URL.revokeObjectURL(source);
    }
    return true;
  }

  Future<Uint8List?> _fetchBlob(String url) async {
    try {
      final response = await web.window.fetch(url.toJS).toDart;
      if (!response.ok) return null;
      final buffer = await response.arrayBuffer().toDart;
      return buffer.toDart.asUint8List();
    } catch (_) {
      // A revoked or already-collected object URL. Nothing recoverable, and
      // the caller treats it as "the recording did not survive".
      return null;
    }
  }

  @override
  Future<Uint8List?> read(String key) async {
    final store = await _store(write: false);
    final result = await _await<JSAny?>(store.get(key.toJS));
    if (result == null) return null;
    return (result as JSUint8Array).toDart;
  }

  @override
  Future<bool> exists(String key) async => (await size(key)) != null;

  @override
  Future<int?> size(String key) async {
    final bytes = await read(key);
    return bytes?.lengthInBytes;
  }

  @override
  Future<void> delete(String key) async {
    final store = await _store(write: true);
    await _await<JSAny?>(store.delete(key.toJS));
  }
}

BlobStore createBlobStore() => IndexedDbBlobStore();
