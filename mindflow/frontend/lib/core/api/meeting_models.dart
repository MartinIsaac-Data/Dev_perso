/// Models for the live meeting layer (API.md §18).
///
/// [SuggestionKind] carries the same defaulting rule as the server: an
/// unrecognised label becomes a *question*, never an action. The direction is
/// the point — an invented question is noise, an invented action asks somebody
/// to do something nobody agreed to.
library;

import 'models.dart' show parseDate;
import 'planning_models.dart' show asMap;

enum MeetingStatus {
  live,
  ended,
  abandoned;

  static MeetingStatus parse(String? value) => switch (value) {
        'live' => MeetingStatus.live,
        'abandoned' => MeetingStatus.abandoned,
        _ => MeetingStatus.ended,
      };

  bool get isLive => this == MeetingStatus.live;

  String get label => switch (this) {
        MeetingStatus.live => 'En cours',
        MeetingStatus.ended => 'Terminée',
        MeetingStatus.abandoned => 'Abandonnée',
      };
}

enum SuggestionKind {
  action,
  decision,
  question;

  /// An unknown kind is a question, not an action. See the library doc.
  static SuggestionKind parse(String? value) => switch (value) {
        'action' => SuggestionKind.action,
        'decision' => SuggestionKind.decision,
        _ => SuggestionKind.question,
      };

  String get label => switch (this) {
        SuggestionKind.action => 'Action',
        SuggestionKind.decision => 'Décision',
        SuggestionKind.question => 'Question ouverte',
      };
}

class MeetingSuggestion {
  const MeetingSuggestion({
    required this.kind,
    required this.text,
    this.owner,
    this.confidence = 0.5,
    this.atWord = 0,
    this.createdAt,
  });

  final SuggestionKind kind;
  final String text;
  final String? owner;
  final double confidence;
  final int atWord;
  final DateTime? createdAt;

  /// Same identity the server deduplicates on, so a suggestion arriving twice —
  /// once on the block response, once on the stream — is shown once.
  String get key => text.trim().toLowerCase();

  factory MeetingSuggestion.fromJson(Map<String, dynamic> json) =>
      MeetingSuggestion(
        kind: SuggestionKind.parse(json['kind'] as String?),
        text: (json['text'] as String?) ?? '',
        owner: json['owner'] as String?,
        confidence: (json['confidence'] as num?)?.toDouble() ?? 0.5,
        atWord: (json['at_word'] as num?)?.toInt() ?? 0,
        createdAt: parseDate(json['created_at']),
      );
}

class Meeting {
  const Meeting({
    required this.id,
    required this.status,
    this.title,
    this.startedAt,
    this.endedAt,
    this.transcript = '',
    this.wordCount = 0,
    this.suggestions = const [],
  });

  final String id;
  final MeetingStatus status;
  final String? title;
  final DateTime? startedAt;
  final DateTime? endedAt;
  final String transcript;
  final int wordCount;
  final List<MeetingSuggestion> suggestions;

  factory Meeting.fromJson(Map<String, dynamic> json) => Meeting(
        id: json['id'] as String,
        status: MeetingStatus.parse(json['status'] as String?),
        title: json['title'] as String?,
        startedAt: parseDate(json['started_at']),
        endedAt: parseDate(json['ended_at']),
        transcript: (json['transcript'] as String?) ?? '',
        wordCount: (json['word_count'] as num?)?.toInt() ?? 0,
        suggestions: ((json['suggestions'] as List<dynamic>?) ?? const [])
            .map((item) => MeetingSuggestion.fromJson(asMap(item)))
            .toList(growable: false),
      );
}

/// What one block produced. The delta, not the whole list, so the panel can
/// animate exactly what appeared.
class MeetingBlock {
  const MeetingBlock({
    required this.meetingId,
    this.wordCount = 0,
    this.newSuggestions = const [],
  });

  final String meetingId;
  final int wordCount;
  final List<MeetingSuggestion> newSuggestions;

  factory MeetingBlock.fromJson(Map<String, dynamic> json) => MeetingBlock(
        meetingId: (json['meeting_id'] as String?) ?? '',
        wordCount: (json['word_count'] as num?)?.toInt() ?? 0,
        newSuggestions:
            ((json['new_suggestions'] as List<dynamic>?) ?? const [])
                .map((item) => MeetingSuggestion.fromJson(asMap(item)))
                .toList(growable: false),
      );
}

class MeetingAction {
  const MeetingAction({required this.text, this.owner, this.due});

  final String text;
  final String? owner;
  final String? due;

  factory MeetingAction.fromJson(Map<String, dynamic> json) => MeetingAction(
        text: (json['text'] as String?) ?? '',
        owner: json['owner'] as String?,
        due: json['due'] as String?,
      );
}

class MeetingReport {
  const MeetingReport({
    this.summary = '',
    this.decisions = const [],
    this.actions = const [],
    this.openQuestions = const [],
    this.degraded = false,
    this.reason = '',
  });

  final String summary;
  final List<String> decisions;
  final List<MeetingAction> actions;
  final List<String> openQuestions;

  /// True when the report is what the live pass had already found rather than a
  /// written summary. Surfaced, never hidden: a degraded report that looks
  /// complete is the failure this whole feature has to avoid.
  final bool degraded;
  final String reason;

  bool get isEmpty =>
      summary.isEmpty &&
      decisions.isEmpty &&
      actions.isEmpty &&
      openQuestions.isEmpty;

  factory MeetingReport.fromJson(Map<String, dynamic> json) => MeetingReport(
        summary: (json['summary'] as String?) ?? '',
        decisions: _strings(json['decisions']),
        actions: ((json['actions'] as List<dynamic>?) ?? const [])
            .map((item) => MeetingAction.fromJson(asMap(item)))
            .toList(growable: false),
        openQuestions: _strings(json['open_questions']),
        degraded: (json['degraded'] as bool?) ?? false,
        reason: (json['reason'] as String?) ?? '',
      );
}

class MeetingOutcome {
  const MeetingOutcome({required this.meeting, required this.report});

  final Meeting meeting;
  final MeetingReport report;

  factory MeetingOutcome.fromJson(Map<String, dynamic> json) => MeetingOutcome(
        meeting: Meeting.fromJson(asMap(json['meeting'])),
        report: MeetingReport.fromJson(asMap(json['report'])),
      );
}

List<String> _strings(dynamic value) => value is List
    ? value.map((item) => item.toString()).toList(growable: false)
    : const <String>[];
