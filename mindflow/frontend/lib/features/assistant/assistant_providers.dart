/// State for the assistant, the knowledge views and the digests.
///
/// The chat controller is the interesting one. It holds the transcript and
/// appends to a *pending* assistant message as fragments arrive, so the list has
/// exactly one source of truth about what it is rendering. The alternative —
/// a separate `streamingText` field beside the message list — means two places
/// that must agree, and they stop agreeing the first time a stream is cancelled
/// mid-answer.
library;

import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/assistant_models.dart';
import '../../core/api/client.dart';

/// The questions the product is built to answer, offered on the empty screen.
///
/// Not decoration: a blank chat box is the hardest interface in software to
/// start using, and these five tell the user what kind of thing this assistant
/// is for far faster than any placeholder text.
const suggestedQuestions = <String>[
  'Que dois-je faire aujourd\'hui ?',
  'Quelles sont mes tâches en retard ?',
  'Résume mes réunions.',
  'Quels sujets reviennent souvent ?',
  'Montre les notes concernant le Forecast Gabon',
];

class ChatState {
  const ChatState({
    this.messages = const [],
    this.conversationId,
    this.sending = false,
    this.error,
  });

  final List<ChatMessage> messages;
  final String? conversationId;
  final bool sending;
  final String? error;

  bool get isEmpty => messages.isEmpty;

  ChatState copyWith({
    List<ChatMessage>? messages,
    String? conversationId,
    bool? sending,
    String? error,
    bool clearError = false,
  }) =>
      ChatState(
        messages: messages ?? this.messages,
        conversationId: conversationId ?? this.conversationId,
        sending: sending ?? this.sending,
        error: clearError ? null : (error ?? this.error),
      );
}

class ChatController extends StateNotifier<ChatState> {
  ChatController(this._api) : super(const ChatState());

  final MindflowApi _api;
  StreamSubscription<AssistantEvent>? _subscription;

  /// Sent with the question so a retry is idempotent. Regenerated only once the
  /// answer has landed — reusing it on a retry is the entire point (ADR-009).
  String? _clientMessageId;

  Future<void> ask(String question) async {
    final text = question.trim();
    if (text.isEmpty || state.sending) return;

    _clientMessageId ??= DateTime.now().microsecondsSinceEpoch.toString();

    // The question and an empty pending answer go in together, so the user sees
    // their message and the assistant's cursor in the same frame rather than
    // watching a gap open and close.
    final pending = ChatMessage(
      id: 'pending',
      role: 'assistant',
      content: '',
      pending: true,
    );
    state = state.copyWith(
      messages: [
        ...state.messages,
        ChatMessage(
            id: 'local-${state.messages.length}', role: 'user', content: text),
        pending,
      ],
      sending: true,
      clearError: true,
    );

    final buffer = StringBuffer();
    try {
      await for (final event in _api.askStreaming(
        text,
        conversationId: state.conversationId,
        clientMessageId: _clientMessageId,
      )) {
        switch (event) {
          case AssistantDelta(:final text):
            buffer.write(text);
            _replacePending(buffer.toString(), pending: true);
          case AssistantDone(:final answer):
            _settle(answer);
        }
      }
      _clientMessageId = null;
    } catch (error) {
      // The pending bubble is removed rather than left half-written: a
      // truncated answer beside an error message reads as though part of it
      // might still be true.
      state = state.copyWith(
        messages:
            state.messages.where((m) => !m.pending).toList(growable: false),
        sending: false,
        error: 'La réponse n\'a pas pu être obtenue. Réessayez.',
      );
      return;
    }
    state = state.copyWith(sending: false);
  }

  void _replacePending(String text, {required bool pending}) {
    final messages = [...state.messages];
    final index = messages.lastIndexWhere((message) => message.pending);
    if (index < 0) return;
    messages[index] = messages[index].copyWith(content: text, pending: pending);
    state = state.copyWith(messages: messages);
  }

  void _settle(Answer answer) {
    final messages = [...state.messages];
    final index = messages.lastIndexWhere((message) => message.pending);
    final settled = ChatMessage.fromAnswer(answer);
    if (index < 0) {
      messages.add(settled);
    } else {
      messages[index] = settled;
    }
    state = state.copyWith(
      messages: messages,
      conversationId: answer.conversationId,
      sending: false,
    );
  }

  /// Start a fresh thread. The previous one is kept server-side and reachable
  /// from the history list — "new conversation" must never mean "lose the last
  /// one".
  void reset() {
    _subscription?.cancel();
    _clientMessageId = null;
    state = const ChatState();
  }

  Future<void> open(String conversationId) async {
    state = ChatState(conversationId: conversationId, sending: true);
    try {
      final messages = await _api.conversationMessages(conversationId);
      state = ChatState(messages: messages, conversationId: conversationId);
    } catch (_) {
      state = ChatState(
        conversationId: conversationId,
        error: 'Conversation illisible.',
      );
    }
  }

  @override
  void dispose() {
    _subscription?.cancel();
    super.dispose();
  }
}

final chatControllerProvider =
    StateNotifierProvider<ChatController, ChatState>((ref) {
  return ChatController(ref.watch(apiProvider));
});

final conversationsProvider = FutureProvider<List<Conversation>>((ref) {
  return ref.watch(apiProvider).listConversations();
});

final entitiesProvider =
    FutureProvider.family<List<KnownEntity>, EntityKind?>((ref, kind) {
  return ref.watch(apiProvider).listEntities(kind: kind);
});

final themesProvider = FutureProvider<List<RecurringTheme>>((ref) {
  return ref.watch(apiProvider).themes();
});

final digestsProvider =
    FutureProvider.family<List<Digest>, DigestPeriod?>((ref, period) {
  return ref.watch(apiProvider).listDigests(period: period);
});

final memoriesProvider = FutureProvider<List<Memory>>((ref) {
  return ref.watch(apiProvider).listMemories();
});

/// Polled by the semantic search screen so "still indexing" and "no answer
/// exists" can be told apart — from outside they look identical.
final indexStatusProvider = FutureProvider<IndexStatus>((ref) {
  return ref.watch(apiProvider).indexStatus();
});

final semanticResultsProvider =
    FutureProvider.family<SemanticResults, String>((ref, query) async {
  if (query.trim().length < 2) return const SemanticResults();
  return ref.watch(apiProvider).semanticSearch(query);
});
