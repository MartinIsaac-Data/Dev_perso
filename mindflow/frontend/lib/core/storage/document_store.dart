/// Small named JSON documents — the pending-capture queue and the preferences.
///
/// Split from `BlobStore` because the two have different shapes and different
/// stakes. These documents are kilobytes of metadata; audio is megabytes. On
/// the web that difference decides the mechanism: `localStorage` is a fine home
/// for a queue of a dozen entries and a hopeless one for a recording.
///
/// Same rule as phase 1: a truncated write must never brick the app. Every
/// caller here treats an unreadable document as an absent one.
library;

import 'document_store_io.dart'
    if (dart.library.js_interop) 'document_store_web.dart' as impl;

abstract class DocumentStore {
  /// Null when the document has never been written, or could not be read.
  Future<String?> read(String name);

  Future<void> write(String name, String contents);

  Future<void> delete(String name);
}

DocumentStore createDocumentStore() => impl.createDocumentStore();
