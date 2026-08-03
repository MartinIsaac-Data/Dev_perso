import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mindflow/core/api/errors.dart';
import 'package:mindflow/core/api/models.dart';
import 'package:mindflow/features/notes/notes_providers.dart';

void main() {
  group('ApiException', () {
    test('classifies by applicative code, not HTTP status', () {
      // 401 and 403 both mean "not signed in" to a user, and two different
      // errors share 409. The code is the stable half of the contract
      // (API.md §6).
      const expired = ApiException(
        code: 'token_expired',
        title: 'Jeton expiré',
        detail: '',
        status: 401,
      );
      const conflict = ApiException(
        code: 'entry_version_conflict',
        title: 'Conflit',
        detail: '',
        status: 409,
      );

      expect(expired.isAuth, isTrue);
      expect(conflict.isConflict, isTrue);
      expect(conflict.isAuth, isFalse);
    });

    test('never shows a raw 5xx detail to the user', () {
      const error = ApiException(
        code: 'internal_error',
        title: 'Erreur',
        detail: 'psycopg.errors.UndefinedColumn: column e.foo does not exist',
        status: 500,
      );
      expect(error.userMessage, isNot(contains('psycopg')));
      expect(error.userMessage, contains('Réessayez'));
    });

    test('says a quota is spent without suggesting anything was lost', () {
      const error = ApiException(
        code: 'quota_exceeded',
        title: 'Quota',
        detail: '',
        status: 402,
      );
      // ADR-026: over the limit, captures are still kept and transcribed.
      expect(error.userMessage, contains('conservées'));
      expect(error.isQuota, isTrue);
    });

    test('decodes a problem document from a Dio error', () {
      final error = ApiException.fromDio(
        DioException(
          requestOptions: RequestOptions(path: '/v1/entries/1'),
          response: Response<Map<String, dynamic>>(
            requestOptions: RequestOptions(path: '/v1/entries/1'),
            statusCode: 409,
            data: const {
              'code': 'entry_version_conflict',
              'title': 'La ressource a été modifiée ailleurs',
              'detail': 'La version fournie ne correspond pas.',
              'request_id': 'req_01J8XKQ2M9',
              'current_version': 5,
            },
          ),
        ),
      );

      expect(error.code, 'entry_version_conflict');
      expect(error.currentVersion, 5);
      expect(error.requestId, 'req_01J8XKQ2M9');
    });

    test('falls back to a transport error when there is no problem document',
        () {
      final error = ApiException.fromDio(
        DioException(
          requestOptions: RequestOptions(path: '/v1/entries'),
          type: DioExceptionType.connectionTimeout,
        ),
      );
      expect(error.code, 'network_error');
      expect(error.userMessage, contains('connexion'));
    });
  });

  group('NotesFilter', () {
    test('maps to the API query values', () {
      const filter =
          NotesFilter(type: EntryType.task, status: EntryStatus.needsReview);
      expect(filter.typeParam, 'task');
      expect(filter.statusParam, 'needs_review');
    });

    test('sends nothing for an unknown enum value', () {
      // A value the server invented and this build does not know must not be
      // echoed back as a filter it cannot honour.
      const filter = NotesFilter(type: EntryType.unknown);
      expect(filter.typeParam, isNull);
    });

    test('clears a facet explicitly', () {
      const filter = NotesFilter(type: EntryType.task, search: 'DAF');
      final cleared = filter.copyWith(clearType: true);
      expect(cleared.type, isNull);
      expect(cleared.search, 'DAF');
    });

    test('compares by value so the provider does not refetch on every rebuild',
        () {
      expect(
        const NotesFilter(type: EntryType.idea, search: 'x'),
        const NotesFilter(type: EntryType.idea, search: 'x'),
      );
    });
  });
}
