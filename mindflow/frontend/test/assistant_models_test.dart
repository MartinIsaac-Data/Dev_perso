/// Parsing the AI layer's payloads.
///
/// Every test here defends against the same class of bug: a field the server
/// stops sending, or sends as a different type, silently becoming a default.
/// A citation list that quietly parses to empty is the worst case — the answer
/// still renders, it just loses the evidence that made it trustworthy.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:mindflow/core/api/assistant_models.dart';

void main() {
  group('AnswerIntent', () {
    test('maps every wire value the backend can send', () {
      expect(AnswerIntent.parse('today'), AnswerIntent.today);
      expect(AnswerIntent.parse('overdue'), AnswerIntent.overdue);
      expect(AnswerIntent.parse('summarise'), AnswerIntent.summarise);
      expect(AnswerIntent.parse('recall'), AnswerIntent.recall);
      expect(AnswerIntent.parse('themes'), AnswerIntent.themes);
      expect(AnswerIntent.parse('open_question'), AnswerIntent.openQuestion);
    });

    test('an unknown value does not crash the screen', () {
      // A backend that adds an intent must not break a client that has not
      // shipped yet.
      expect(AnswerIntent.parse('teleportation'), AnswerIntent.unknown);
      expect(AnswerIntent.parse(null), AnswerIntent.unknown);
    });

    test('only retrieval-backed answers expect citations', () {
      // A structured answer has no sources to show, and an empty "sources"
      // strip under it would read as a failure.
      expect(AnswerIntent.summarise.needsCitations, isTrue);
      expect(AnswerIntent.recall.needsCitations, isTrue);
      expect(AnswerIntent.openQuestion.needsCitations, isTrue);
      expect(AnswerIntent.today.needsCitations, isFalse);
      expect(AnswerIntent.overdue.needsCitations, isFalse);
    });

    test('every intent has a French label', () {
      for (final intent in AnswerIntent.values) {
        expect(intent.label, isNotEmpty);
      }
    });
  });

  group('Answer', () {
    test('parses a complete payload', () {
      final answer = Answer.fromJson({
        'text': 'Deux tâches aujourd\'hui.',
        'intent': 'today',
        'citations': [
          {
            'ref': 'c1',
            'title': 'Réunion du 3 mars',
            'excerpt': 'On a parlé du forecast.',
            'entry_id': 'e1',
            'occurred_at': '2026-03-03',
            'score': 0.42,
          }
        ],
        'notes': ['Réponse construite depuis vos échéances.'],
        'conversation_id': 'conv-1',
        'message_id': 'msg-1',
        'latency_ms': 42,
        'used_model': false,
      });

      expect(answer.intent, AnswerIntent.today);
      expect(answer.citations.single.title, 'Réunion du 3 mars');
      expect(answer.citations.single.score, 0.42);
      expect(answer.notes.single, startsWith('Réponse construite'));
      expect(answer.usedModel, isFalse);
      expect(answer.latencyMs, 42);
    });

    test('a payload with nothing but text still parses', () {
      // Defensive on purpose: a missing citations array must yield an empty
      // list, never a null that throws while the answer is being rendered.
      final answer = Answer.fromJson({'text': 'Bonjour'});
      expect(answer.text, 'Bonjour');
      expect(answer.citations, isEmpty);
      expect(answer.notes, isEmpty);
      expect(answer.intent, AnswerIntent.unknown);
    });

    test('citations survive being hand-written as dynamic maps', () {
      // Nested JSON decodes as Map<dynamic, dynamic> in several code paths;
      // `asMap` is what stops that from throwing at the cast.
      final answer = Answer.fromJson({
        'text': 'x',
        'citations': [
          <dynamic, dynamic>{'ref': 'c1', 'title': 'T', 'excerpt': 'E'}
        ],
      });
      expect(answer.citations.single.ref, 'c1');
    });
  });

  group('ChatMessage', () {
    test('distinguishes the two roles', () {
      expect(
        const ChatMessage(id: '1', role: 'user', content: 'q').isUser,
        isTrue,
      );
      expect(
        const ChatMessage(id: '2', role: 'assistant', content: 'a').isUser,
        isFalse,
      );
    });

    test('copyWith changes the content and keeps everything else', () {
      const original = ChatMessage(
        id: '1',
        role: 'assistant',
        content: 'Deux',
        intent: AnswerIntent.summarise,
        pending: true,
      );
      final updated = original.copyWith(content: 'Deux tâches', pending: false);

      expect(updated.content, 'Deux tâches');
      expect(updated.pending, isFalse);
      expect(updated.intent, AnswerIntent.summarise);
      expect(updated.id, '1');
    });

    test('is built from an answer with its citations intact', () {
      const answer = Answer(
        text: 'Réponse',
        intent: AnswerIntent.recall,
        messageId: 'm1',
        citations: [Citation(ref: 'c1', title: 'T', excerpt: 'E')],
      );
      final message = ChatMessage.fromAnswer(answer);

      expect(message.id, 'm1');
      expect(message.role, 'assistant');
      expect(message.citations, hasLength(1));
    });
  });

  group('Digest', () {
    test('parses stats as integers', () {
      final digest = Digest.fromJson({
        'id': 'd1',
        'period': 'weekly',
        'period_start': '2026-06-01',
        'period_end': '2026-06-07',
        'content': 'Une semaine chargée.',
        'stats': {'entries_created': 12, 'tasks_completed': 5},
      });

      expect(digest.period, DigestPeriod.weekly);
      expect(digest.stats['entries_created'], 12);
      expect(digest.isRead, isFalse);
    });

    test('an unknown period falls back to daily rather than throwing', () {
      expect(DigestPeriod.parse('quarterly'), DigestPeriod.daily);
    });
  });

  group('Memory', () {
    test('a long-unconfirmed fact is marked as fading', () {
      // Surfaced so the user can see why the assistant treats a fact from March
      // differently from one confirmed yesterday.
      final fading = Memory.fromJson({
        'id': 'm1',
        'kind': 'profile',
        'label': 'Profil',
        'statement': 'Je dirige le pôle forecast',
        'weight': 0.3,
      });
      final fresh = Memory.fromJson({
        'id': 'm2',
        'kind': 'profile',
        'label': 'Profil',
        'statement': 'x',
        'weight': 0.9,
      });

      expect(fading.isFading, isTrue);
      expect(fresh.isFading, isFalse);
    });
  });

  group('IndexStatus', () {
    test('distinguishes still-indexing from nothing-to-find', () {
      // These look identical from outside — an empty result either way — which
      // is precisely why the status exists.
      const indexing = IndexStatus(totalChunks: 100, pendingChunks: 40);
      const ready = IndexStatus(totalChunks: 100, pendingChunks: 0);

      expect(indexing.isIndexing, isTrue);
      expect(indexing.progress, closeTo(0.6, 0.001));
      expect(ready.isIndexing, isFalse);
      expect(ready.progress, 1);
    });

    test('an empty corpus reads as complete, not as zero progress', () {
      // Otherwise a brand-new account shows a permanently empty progress bar.
      const empty = IndexStatus();
      expect(empty.progress, 1);
      expect(empty.isIndexing, isFalse);
    });
  });

  group('Passage', () {
    test('agreement between retrievers is visible', () {
      const both = Passage(
        chunkId: 'c1',
        text: 't',
        title: 'T',
        foundBy: ['lexical', 'semantic'],
      );
      const one =
          Passage(chunkId: 'c2', text: 't', title: 'T', foundBy: ['lexical']);

      expect(both.isConsensus, isTrue);
      expect(one.isConsensus, isFalse);
    });
  });

  group('EntityKind', () {
    test('covers the seven kinds the product detects', () {
      final kinds = EntityKind.values.where((k) => k != EntityKind.unknown);
      expect(kinds, hasLength(7));
      for (final kind in kinds) {
        expect(kind.label, isNotEmpty);
        expect(EntityKind.parse(kind.param), kind);
      }
    });

    test('an unknown kind does not crash the list', () {
      expect(EntityKind.parse('cyborg'), EntityKind.unknown);
    });
  });
}
