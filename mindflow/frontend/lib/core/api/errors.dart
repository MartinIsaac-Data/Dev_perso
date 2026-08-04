/// API errors, decoded from RFC 9457 problem documents (docs/API.md §6).
///
/// The client branches on `code`, never on the HTTP status: several errors share
/// a status, and the applicative code is the stable part of the contract.
library;

import 'package:dio/dio.dart';

class ApiException implements Exception {
  const ApiException({
    required this.code,
    required this.title,
    required this.detail,
    this.status,
    this.requestId,
    this.currentVersion,
  });

  final String code;
  final String title;
  final String detail;
  final int? status;

  /// Quoted by the user when reporting a problem; the only way to find the
  /// request in the server logs.
  final String? requestId;
  final int? currentVersion;

  bool get isAuth => code == 'token_expired' || code == 'unauthenticated';

  /// The request never reached the server. Distinct from every other failure
  /// because it is the one the offline queue exists for: nothing is lost, and
  /// the user must be told that rather than that something went wrong.
  bool get isOffline => code == 'network_error';
  bool get isConflict => code == 'entry_version_conflict';
  bool get isQuota => code == 'quota_exceeded';

  /// What to show a user. Never the raw detail for a 5xx — that is for logs.
  String get userMessage => switch (code) {
        'quota_exceeded' =>
          'Quota mensuel atteint. Vos captures sont conservées et transcrites.',
        'capture_too_long' => 'Cet enregistrement est trop long.',
        'content_not_processed' =>
          "Cette capture n'a pas pu être structurée automatiquement. "
              'La transcription reste disponible.',
        'transcription_unavailable' =>
          'La transcription est momentanément indisponible. Votre audio est conservé.',
        'extraction_unavailable' =>
          "L'analyse est momentanément indisponible. Votre transcription est conservée.",
        'entry_version_conflict' =>
          'Cette entrée a été modifiée ailleurs. Rechargez pour voir la version à jour.',
        'resource_not_found' => 'Introuvable.',
        // Deliberately neutral: this message is read on the search screen and
        // the assistant as well as during a capture. The reassurance that
        // nothing was lost belongs to the caller that knows something was
        // queued — see `isOffline` and `CaptureController`.
        'network_error' => 'Pas de réseau. Vérifiez votre connexion.',
        'internal_error' =>
          'Une erreur est survenue. Réessayez dans un instant.',
        _ => detail,
      };

  factory ApiException.fromDio(DioException error) {
    final data = error.response?.data;
    if (data is Map) {
      return ApiException(
        code: (data['code'] as String?) ?? 'internal_error',
        title: (data['title'] as String?) ?? 'Erreur',
        detail: (data['detail'] as String?) ?? 'Une erreur est survenue.',
        status: error.response?.statusCode,
        requestId: data['request_id'] as String?,
        currentVersion: (data['current_version'] as num?)?.toInt(),
      );
    }
    // No problem document: a transport failure, not an API response.
    return ApiException(
      code: 'network_error',
      title: 'Connexion impossible',
      detail: 'Vérifiez votre connexion réseau.',
      status: error.response?.statusCode,
    );
  }

  @override
  String toString() => 'ApiException($code): $detail';
}
