/// HTTP client for the MindFlow API.
library;

import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'errors.dart';
import 'models.dart';

/// Injected at build time: `--dart-define=MINDFLOW_API_BASE_URL=...`
const kApiBaseUrl = String.fromEnvironment(
  'MINDFLOW_API_BASE_URL',
  defaultValue: 'http://localhost:8000',
);

typedef TokenProvider = Future<String?> Function();

class MindflowApi {
  MindflowApi({required TokenProvider tokenProvider, Dio? dio})
      : _tokenProvider = tokenProvider,
        _dio = dio ??
            Dio(
              BaseOptions(
                baseUrl: kApiBaseUrl,
                connectTimeout: const Duration(seconds: 10),
                receiveTimeout: const Duration(seconds: 30),
                headers: {'accept': 'application/json'},
                // Errors are decoded from the problem document, so let every
                // status through rather than having Dio throw on 4xx.
                validateStatus: (status) => status != null && status < 500,
              ),
            ) {
    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          final token = await _tokenProvider();
          if (token != null) {
            options.headers['authorization'] = 'Bearer $token';
          }
          handler.next(options);
        },
      ),
    );
  }

  final Dio _dio;
  final TokenProvider _tokenProvider;

  Future<Map<String, dynamic>> _get(String path,
      {Map<String, dynamic>? query}) async {
    final response =
        await _dio.get<Map<String, dynamic>>(path, queryParameters: query);
    return _unwrap(response);
  }

  Future<Map<String, dynamic>> _post(String path, {Object? body}) async {
    final response = await _dio.post<Map<String, dynamic>>(path, data: body);
    return _unwrap(response);
  }

  Map<String, dynamic> _unwrap(Response<Map<String, dynamic>> response) {
    final data = response.data ?? const <String, dynamic>{};
    if ((response.statusCode ?? 500) >= 400) {
      throw ApiException(
        code: (data['code'] as String?) ?? 'internal_error',
        title: (data['title'] as String?) ?? 'Erreur',
        detail: (data['detail'] as String?) ?? 'Une erreur est survenue.',
        status: response.statusCode,
        requestId: data['request_id'] as String?,
        currentVersion: (data['current_version'] as num?)?.toInt(),
      );
    }
    return data;
  }

  // -- Captures -----------------------------------------------------------

  /// Declare a capture and obtain a signed upload URL.
  ///
  /// [clientCaptureId] is generated on the device *before* recording: replaying
  /// this call after a lost response returns the same capture instead of
  /// creating a duplicate (ADR-009).
  Future<DeclaredCapture> declareCapture({
    required String clientCaptureId,
    required int durationMs,
    required DateTime capturedAt,
    required String timezone,
    String audioFormat = 'm4a',
    int? audioBytes,
    String? languageHint,
    String source = 'app',
  }) async {
    final data = await _post(
      '/v1/captures',
      body: {
        'client_capture_id': clientCaptureId,
        'kind': 'quick',
        'duration_ms': durationMs,
        'audio_format': audioFormat,
        if (audioBytes != null) 'audio_bytes': audioBytes,
        'captured_at': capturedAt.toUtc().toIso8601String(),
        'capture_timezone': timezone,
        'source': source,
        if (languageHint != null) 'language_hint': languageHint,
      },
    );
    return DeclaredCapture.fromJson(data['data'] as Map<String, dynamic>);
  }

  /// Upload the audio straight to storage. It never transits the API (ADR-018).
  Future<void> uploadAudio({
    required String url,
    required Uint8List bytes,
    required Map<String, String> headers,
  }) async {
    final response = await Dio().putUri<void>(
      Uri.parse(url),
      data: Stream.fromIterable([bytes]),
      options: Options(
        headers: {...headers, 'content-length': bytes.length},
        validateStatus: (status) => status != null && status < 500,
      ),
    );
    final status = response.statusCode ?? 500;
    if (status >= 400) {
      throw ApiException(
        code: 'upload_failed',
        title: 'Envoi impossible',
        detail: "L'envoi de l'audio a échoué (HTTP $status).",
        status: status,
      );
    }
  }

  Future<Capture> completeCapture(String captureId) async {
    final data = await _post('/v1/captures/$captureId/complete');
    return Capture.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<Capture> getCapture(String captureId) async {
    final data = await _get('/v1/captures/$captureId');
    return Capture.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<List<Capture>> listCaptures({int limit = 50}) async {
    final data = await _get('/v1/captures', query: {'limit': limit});
    return ((data['data'] as List<dynamic>?) ?? const [])
        .map((e) => Capture.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<void> deleteCapture(String captureId, {bool cascade = false}) async {
    await _dio.delete<void>(
      '/v1/captures/$captureId',
      queryParameters: {'cascade': cascade},
    );
  }

  // -- Entries ------------------------------------------------------------

  Future<List<Entry>> listEntries({
    String? entryType,
    String? status,
    String? search,
    int limit = 100,
  }) async {
    final data = await _get(
      '/v1/entries',
      query: {
        if (entryType != null) 'entry_type': entryType,
        if (status != null) 'status': status,
        if (search != null && search.isNotEmpty) 'q': search,
        'limit': limit,
      },
    );
    return ((data['data'] as List<dynamic>?) ?? const [])
        .map((e) => Entry.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<Entry> getEntry(String entryId) async {
    final data = await _get('/v1/entries/$entryId');
    return Entry.fromJson(data['data'] as Map<String, dynamic>);
  }

  /// Partial update with optimistic locking.
  ///
  /// [expectedVersion] is sent as `If-Match`; a 409 carries the server state so
  /// the caller can merge rather than pick a winner (API.md §8.2).
  Future<Entry> updateEntry(
    String entryId,
    Map<String, dynamic> changes, {
    int? expectedVersion,
  }) async {
    final response = await _dio.patch<Map<String, dynamic>>(
      '/v1/entries/$entryId',
      data: changes,
      options: Options(
        headers: {
          if (expectedVersion != null) 'If-Match': '"$expectedVersion"'
        },
      ),
    );
    return Entry.fromJson(_unwrap(response)['data'] as Map<String, dynamic>);
  }

  Future<Entry> completeEntry(String entryId) async {
    final data = await _post('/v1/entries/$entryId/complete');
    return Entry.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<Entry> createEntry({
    required String title,
    String entryType = 'note',
    String? body,
    String? dueExpression,
  }) async {
    final data = await _post(
      '/v1/entries',
      body: {
        'entry_type': entryType,
        'title': title,
        if (body != null) 'body': body,
        if (dueExpression != null) 'due_expression': dueExpression,
      },
    );
    return Entry.fromJson(data['data'] as Map<String, dynamic>);
  }

  Future<void> deleteEntry(String entryId) async {
    await _dio.delete<void>('/v1/entries/$entryId');
  }

  // -- Dashboard ----------------------------------------------------------

  Future<Dashboard> dashboard() async {
    final data = await _get('/v1/dashboard');
    return Dashboard.fromJson(data['data'] as Map<String, dynamic>);
  }
}

final apiProvider = Provider<MindflowApi>((ref) {
  throw UnimplementedError('apiProvider must be overridden at app start');
});
