/// Models for the AI layer: answers, citations, entities, digests, memory.
///
/// [Citation] is the type that matters. Every generated answer carries the
/// passages it was built from, and the chat screen renders them under the text
/// — not as a nicety but because an answer whose sources are invisible is
/// indistinguishable from one that was invented, and the reader has no way to
/// tell which they are looking at.
library;

import 'planning_models.dart' show asMap;

/// How the assistant answered. Mirrors `app.domain.intent.Intent`.
///
/// The client cares about this for one reason: [needsCitations]. A structured
/// answer is a list the database produced and has nothing to cite, so showing
/// an empty "sources" section under it would look like a failure rather than
/// what it is — an answer that needed no sources.
enum AnswerIntent {
  today,
  overdue,
  upcoming,
  summarise,
  recall,
  themes,
  people,
  openQuestion,
  unknown;

  static AnswerIntent parse(String? value) => switch (value) {
        'today' => AnswerIntent.today,
        'overdue' => AnswerIntent.overdue,
        'upcoming' => AnswerIntent.upcoming,
        'summarise' => AnswerIntent.summarise,
        'recall' => AnswerIntent.recall,
        'themes' => AnswerIntent.themes,
        'people' => AnswerIntent.people,
        'open_question' => AnswerIntent.openQuestion,
        _ => AnswerIntent.unknown,
      };

  /// Whether an answer of this kind is built from retrieved passages.
  bool get needsCitations => switch (this) {
        AnswerIntent.summarise ||
        AnswerIntent.recall ||
        AnswerIntent.openQuestion =>
          true,
        _ => false,
      };

  String get label => switch (this) {
        AnswerIntent.today => 'Aujourd\'hui',
        AnswerIntent.overdue => 'En retard',
        AnswerIntent.upcoming => 'À venir',
        AnswerIntent.summarise => 'Résumé',
        AnswerIntent.recall => 'Recherche',
        AnswerIntent.themes => 'Thèmes',
        AnswerIntent.people => 'Personnes',
        AnswerIntent.openQuestion => 'Question',
        AnswerIntent.unknown => 'Réponse',
      };
}

class Citation {
  const Citation({
    required this.ref,
    required this.title,
    required this.excerpt,
    this.entryId,
    this.captureId,
    this.occurredAt,
    this.score = 0,
  });

  final String ref;
  final String title;
  final String excerpt;
  final String? entryId;
  final String? captureId;
  final String? occurredAt;
  final double score;

  factory Citation.fromJson(Map<String, dynamic> json) => Citation(
        ref: json['ref'] as String? ?? '',
        title: json['title'] as String? ?? 'Sans titre',
        excerpt: json['excerpt'] as String? ?? '',
        entryId: json['entry_id'] as String?,
        captureId: json['capture_id'] as String?,
        occurredAt: json['occurred_at'] as String?,
        score: (json['score'] as num?)?.toDouble() ?? 0,
      );
}

class Answer {
  const Answer({
    required this.text,
    required this.intent,
    this.citations = const [],
    this.notes = const [],
    this.conversationId,
    this.messageId,
    this.latencyMs = 0,
    this.usedModel = false,
    this.refused = false,
  });

  final String text;
  final AnswerIntent intent;
  final List<Citation> citations;

  /// How the answer was produced, in French. Rendered under the answer: an
  /// assistant that says how it answered is one a user can correct.
  final List<String> notes;

  final String? conversationId;
  final String? messageId;
  final int latencyMs;

  /// False for the structured routes. The UI shows those instantly rather than
  /// animating a typing indicator over an answer that is already complete.
  final bool usedModel;
  final bool refused;

  factory Answer.fromJson(Map<String, dynamic> json) => Answer(
        text: json['text'] as String? ?? '',
        intent: AnswerIntent.parse(json['intent'] as String?),
        citations: (json['citations'] as List<dynamic>? ?? const [])
            .map((item) => Citation.fromJson(asMap(item)))
            .toList(growable: false),
        notes: (json['notes'] as List<dynamic>? ?? const [])
            .map((item) => item.toString())
            .toList(growable: false),
        conversationId: json['conversation_id'] as String?,
        messageId: json['message_id'] as String?,
        latencyMs: (json['latency_ms'] as num?)?.toInt() ?? 0,
        usedModel: json['used_model'] as bool? ?? false,
        refused: json['refused'] as bool? ?? false,
      );
}

class ChatMessage {
  const ChatMessage({
    required this.id,
    required this.role,
    required this.content,
    this.intent = AnswerIntent.unknown,
    this.citations = const [],
    this.createdAt,
    this.pending = false,
  });

  final String id;
  final String role;
  final String content;
  final AnswerIntent intent;
  final List<Citation> citations;
  final DateTime? createdAt;

  /// True while the answer is still streaming. Held on the message rather than
  /// in a separate flag so the list has exactly one source of truth about what
  /// it is rendering.
  final bool pending;

  bool get isUser => role == 'user';

  ChatMessage copyWith({String? content, bool? pending}) => ChatMessage(
        id: id,
        role: role,
        content: content ?? this.content,
        intent: intent,
        citations: citations,
        createdAt: createdAt,
        pending: pending ?? this.pending,
      );

  factory ChatMessage.fromJson(Map<String, dynamic> json) => ChatMessage(
        id: json['id'] as String? ?? '',
        role: json['role'] as String? ?? 'assistant',
        content: json['content'] as String? ?? '',
        intent: AnswerIntent.parse(json['intent'] as String?),
        citations: (json['citations'] as List<dynamic>? ?? const [])
            .map((item) => Citation.fromJson(asMap(item)))
            .toList(growable: false),
        createdAt: DateTime.tryParse(json['created_at'] as String? ?? ''),
      );

  factory ChatMessage.fromAnswer(Answer answer) => ChatMessage(
        id: answer.messageId ?? '',
        role: 'assistant',
        content: answer.text,
        intent: answer.intent,
        citations: answer.citations,
        createdAt: DateTime.now(),
      );
}

class Conversation {
  const Conversation({
    required this.id,
    this.title,
    this.messageCount = 0,
    this.lastMessageAt,
  });

  final String id;
  final String? title;
  final int messageCount;
  final DateTime? lastMessageAt;

  factory Conversation.fromJson(Map<String, dynamic> json) => Conversation(
        id: json['id'] as String? ?? '',
        title: json['title'] as String?,
        messageCount: (json['message_count'] as num?)?.toInt() ?? 0,
        lastMessageAt:
            DateTime.tryParse(json['last_message_at'] as String? ?? ''),
      );
}

/// The seven things the product detects automatically.
enum EntityKind {
  person,
  product,
  company,
  project,
  decision,
  risk,
  action,
  unknown;

  static EntityKind parse(String? value) => switch (value) {
        'person' => EntityKind.person,
        'product' => EntityKind.product,
        'company' => EntityKind.company,
        'project' => EntityKind.project,
        'decision' => EntityKind.decision,
        'risk' => EntityKind.risk,
        'action' => EntityKind.action,
        _ => EntityKind.unknown,
      };

  String get label => switch (this) {
        EntityKind.person => 'Personne',
        EntityKind.product => 'Produit',
        EntityKind.company => 'Entreprise',
        EntityKind.project => 'Projet',
        EntityKind.decision => 'Décision',
        EntityKind.risk => 'Risque',
        EntityKind.action => 'Action',
        EntityKind.unknown => 'Autre',
      };

  String get param => name;
}

class KnownEntity {
  const KnownEntity({
    required this.id,
    required this.kind,
    required this.name,
    this.detail,
    this.mentionCount = 0,
    this.lastSeenAt,
  });

  final String id;
  final EntityKind kind;
  final String name;
  final String? detail;
  final int mentionCount;
  final DateTime? lastSeenAt;

  factory KnownEntity.fromJson(Map<String, dynamic> json) => KnownEntity(
        id: json['id'] as String? ?? '',
        kind: EntityKind.parse(json['kind'] as String?),
        name: json['name'] as String? ?? '',
        detail: json['detail'] as String?,
        mentionCount: (json['mention_count'] as num?)?.toInt() ?? 0,
        lastSeenAt: DateTime.tryParse(json['last_seen_at'] as String? ?? ''),
      );
}

/// A subject that keeps coming back.
///
/// Named `RecurringTheme` rather than `Theme` because Flutter already owns that
/// word, and a model class that shadows a framework widget makes every file
/// that imports both ambiguous.
class RecurringTheme {
  const RecurringTheme({
    required this.kind,
    required this.name,
    required this.count,
  });

  final EntityKind kind;
  final String name;
  final int count;

  factory RecurringTheme.fromJson(Map<String, dynamic> json) => RecurringTheme(
        kind: EntityKind.parse(json['kind'] as String?),
        name: json['name'] as String? ?? '',
        count: (json['count'] as num?)?.toInt() ?? 0,
      );
}

enum DigestPeriod {
  daily,
  weekly,
  monthly;

  static DigestPeriod parse(String? value) => switch (value) {
        'weekly' => DigestPeriod.weekly,
        'monthly' => DigestPeriod.monthly,
        _ => DigestPeriod.daily,
      };

  String get param => name;

  String get label => switch (this) {
        DigestPeriod.daily => 'Quotidien',
        DigestPeriod.weekly => 'Hebdomadaire',
        DigestPeriod.monthly => 'Mensuel',
      };
}

class Digest {
  const Digest({
    required this.id,
    required this.period,
    required this.periodStart,
    required this.periodEnd,
    required this.content,
    this.stats = const {},
    this.entryCount = 0,
    this.readAt,
  });

  final String id;
  final DigestPeriod period;
  final DateTime periodStart;
  final DateTime periodEnd;
  final String content;
  final Map<String, int> stats;
  final int entryCount;
  final DateTime? readAt;

  bool get isRead => readAt != null;

  factory Digest.fromJson(Map<String, dynamic> json) => Digest(
        id: json['id'] as String? ?? '',
        period: DigestPeriod.parse(json['period'] as String?),
        periodStart: DateTime.tryParse(json['period_start'] as String? ?? '') ??
            DateTime.now(),
        periodEnd: DateTime.tryParse(json['period_end'] as String? ?? '') ??
            DateTime.now(),
        content: json['content'] as String? ?? '',
        stats: asMap(json['stats']).map(
          (key, value) => MapEntry(key, (value as num?)?.toInt() ?? 0),
        ),
        entryCount: (json['entry_count'] as num?)?.toInt() ?? 0,
        readAt: DateTime.tryParse(json['read_at'] as String? ?? ''),
      );
}

class Memory {
  const Memory({
    required this.id,
    required this.kind,
    required this.label,
    required this.statement,
    this.confidence = 0,
    this.weight = 1,
    this.confirmedAt,
  });

  final String id;
  final String kind;
  final String label;
  final String statement;
  final double confidence;

  /// How much this memory still counts after decay. Surfaced so the user can
  /// see that a fact from March is weighted differently from one confirmed
  /// yesterday, rather than wondering why the assistant "half-remembers".
  final double weight;

  final DateTime? confirmedAt;

  bool get isFading => weight < 0.5;

  factory Memory.fromJson(Map<String, dynamic> json) => Memory(
        id: json['id'] as String? ?? '',
        kind: json['kind'] as String? ?? 'profile',
        label: json['label'] as String? ?? 'Profil',
        statement: json['statement'] as String? ?? '',
        confidence: (json['confidence'] as num?)?.toDouble() ?? 0,
        weight: (json['weight'] as num?)?.toDouble() ?? 1,
        confirmedAt: DateTime.tryParse(json['confirmed_at'] as String? ?? ''),
      );
}

class Passage {
  const Passage({
    required this.chunkId,
    required this.text,
    required this.title,
    this.entryId,
    this.occurredAt,
    this.foundBy = const [],
    this.score = 0,
  });

  final String chunkId;
  final String text;
  final String title;
  final String? entryId;
  final String? occurredAt;

  /// Which retrievers found this passage. Shown to the user because agreement
  /// between meaning and words is a much stronger signal than either alone.
  final List<String> foundBy;

  final double score;

  bool get isConsensus => foundBy.length > 1;

  factory Passage.fromJson(Map<String, dynamic> json) => Passage(
        chunkId: json['chunk_id'] as String? ?? '',
        text: json['text'] as String? ?? '',
        title: json['title'] as String? ?? '',
        entryId: json['entry_id'] as String?,
        occurredAt: json['occurred_at'] as String?,
        foundBy: (json['found_by'] as List<dynamic>? ?? const [])
            .map((item) => item.toString())
            .toList(growable: false),
        score: (json['score'] as num?)?.toDouble() ?? 0,
      );
}

class SemanticResults {
  const SemanticResults({
    this.passages = const [],
    this.tookMs = 0,
    this.lexicalCount = 0,
    this.semanticCount = 0,
    this.notes = const [],
  });

  final List<Passage> passages;
  final int tookMs;
  final int lexicalCount;
  final int semanticCount;
  final List<String> notes;

  factory SemanticResults.fromJson(Map<String, dynamic> json) =>
      SemanticResults(
        passages: (json['passages'] as List<dynamic>? ?? const [])
            .map((item) => Passage.fromJson(asMap(item)))
            .toList(growable: false),
        tookMs: (json['took_ms'] as num?)?.toInt() ?? 0,
        lexicalCount: (json['lexical_count'] as num?)?.toInt() ?? 0,
        semanticCount: (json['semantic_count'] as num?)?.toInt() ?? 0,
        notes: (json['notes'] as List<dynamic>? ?? const [])
            .map((item) => item.toString())
            .toList(growable: false),
      );
}

class IndexStatus {
  const IndexStatus({
    this.totalChunks = 0,
    this.pendingChunks = 0,
    this.provider = 'none',
  });

  final int totalChunks;
  final int pendingChunks;
  final String provider;

  /// Whether the corpus is still being made searchable by meaning. Shown so a
  /// user whose semantic search returns nothing can tell "still indexing" from
  /// "no answer exists" — otherwise the two look identical.
  bool get isIndexing => pendingChunks > 0;

  double get progress =>
      totalChunks == 0 ? 1 : (totalChunks - pendingChunks) / totalChunks;

  factory IndexStatus.fromJson(Map<String, dynamic> json) => IndexStatus(
        totalChunks: (json['total_chunks'] as num?)?.toInt() ?? 0,
        pendingChunks: (json['pending_chunks'] as num?)?.toInt() ?? 0,
        provider: json['provider'] as String? ?? 'none',
      );
}
