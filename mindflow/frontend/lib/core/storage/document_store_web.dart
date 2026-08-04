/// Browser document storage: `localStorage`.
///
/// The right tool here and the wrong one for audio. These documents are small,
/// read on every start and written once per capture; `localStorage` is
/// synchronous, survives a reload, and needs no schema. IndexedDB would work
/// too and would cost an open, a transaction and an upgrade path for a value
/// that fits in a few kilobytes.
///
/// Keys are prefixed so the store shares an origin with anything else the page
/// keeps without colliding with it.
library;

import 'package:web/web.dart' as web;

import 'document_store.dart';

const _prefix = 'mindflow.';

class LocalStorageDocumentStore implements DocumentStore {
  @override
  Future<String?> read(String name) async {
    try {
      return web.window.localStorage.getItem('$_prefix$name');
    } catch (_) {
      // Private browsing in some engines makes `localStorage` throw on access
      // rather than merely be empty. An absent document is the honest answer.
      return null;
    }
  }

  @override
  Future<void> write(String name, String contents) async {
    try {
      web.window.localStorage.setItem('$_prefix$name', contents);
    } catch (_) {
      // Quota exceeded, or storage disabled. The queue degrades to
      // in-session-only, which the capture screen already surfaces.
    }
  }

  @override
  Future<void> delete(String name) async {
    try {
      web.window.localStorage.removeItem('$_prefix$name');
    } catch (_) {
      // See above.
    }
  }
}

DocumentStore createDocumentStore() => LocalStorageDocumentStore();
