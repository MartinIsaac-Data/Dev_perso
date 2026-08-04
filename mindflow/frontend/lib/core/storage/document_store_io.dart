/// Native document storage: one JSON file per name, as in phase 1.
library;

import 'dart:io';

import 'package:path_provider/path_provider.dart';

import 'document_store.dart';

class FileDocumentStore implements DocumentStore {
  FileDocumentStore({Directory? directory}) : _directory = directory;

  final Directory? _directory;
  Directory? _resolved;

  Future<Directory> _base() async =>
      _resolved ??= _directory ?? await getApplicationDocumentsDirectory();

  Future<File> _file(String name) async =>
      File('${(await _base()).path}/$name');

  @override
  Future<String?> read(String name) async {
    final file = await _file(name);
    if (!file.existsSync()) return null;
    try {
      return await file.readAsString();
    } on FileSystemException {
      return null;
    }
  }

  @override
  Future<void> write(String name, String contents) async {
    final file = await _file(name);
    await file.writeAsString(contents, flush: true);
  }

  @override
  Future<void> delete(String name) async {
    final file = await _file(name);
    if (file.existsSync()) {
      try {
        await file.delete();
      } on FileSystemException {
        // Best effort: the caller is already treating it as absent.
      }
    }
  }
}

DocumentStore createDocumentStore() => FileDocumentStore();
