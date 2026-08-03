/// Data transfer objects mirroring the API contract (docs/API.md §3.2).
///
/// Every collection response is wrapped in `data`; every object carries an
/// `object` discriminator. Unknown enum values are mapped to a neutral fallback
/// rather than throwing — API.md §12.2 requires clients to tolerate values added
/// server-side, and a crash on an unknown string is exactly what that forbids.
library;

class Envelope<T> {
  const Envelope(this.data);
  final T data;
}

enum EntryType {
  task,
  idea,
  note,
  decision,
  question,
  meeting,
  reminder,
  unknown
}

EntryType entryTypeFrom(String? raw) => switch (raw) {
      'task' => EntryType.task,
      'idea' => EntryType.idea,
      'note' => EntryType.note,
      'decision' => EntryType.decision,
      'question' => EntryType.question,
      'meeting' => EntryType.meeting,
      'reminder' => EntryType.reminder,
      _ => EntryType.unknown,
    };

enum EntryStatus { needsReview, active, done, archived, snoozed, unknown }

EntryStatus entryStatusFrom(String? raw) => switch (raw) {
      'needs_review' => EntryStatus.needsReview,
      'active' => EntryStatus.active,
      'done' => EntryStatus.done,
      'archived' => EntryStatus.archived,
      'snoozed' => EntryStatus.snoozed,
      _ => EntryStatus.unknown,
    };

enum CaptureStatus {
  pendingUpload,
  uploaded,
  transcribing,
  transcribed,
  extracting,
  completed,
  partiallyProcessed,
  transcriptionFailed,
  abandoned,
  unknown;

  bool get isTerminal => const {
        CaptureStatus.completed,
        CaptureStatus.partiallyProcessed,
        CaptureStatus.transcriptionFailed,
        CaptureStatus.abandoned,
      }.contains(this);

  bool get isProcessing => !isTerminal && this != CaptureStatus.pendingUpload;
}

CaptureStatus captureStatusFrom(String? raw) => switch (raw) {
      'pending_upload' => CaptureStatus.pendingUpload,
      'uploaded' => CaptureStatus.uploaded,
      'transcribing' => CaptureStatus.transcribing,
      'transcribed' => CaptureStatus.transcribed,
      'extracting' => CaptureStatus.extracting,
      'completed' => CaptureStatus.completed,
      'partially_processed' => CaptureStatus.partiallyProcessed,
      'transcription_failed' => CaptureStatus.transcriptionFailed,
      'abandoned' => CaptureStatus.abandoned,
      _ => CaptureStatus.unknown,
    };

class TaskDetails {
  const TaskDetails({
    this.dueAt,
    this.duePrecision,
    this.dueRawExpression,
    this.priority = 'normal',
    this.completedAt,
    this.assigneeLabel,
    this.recurrenceRule,
    this.snoozedUntil,
  });

  final DateTime? dueAt;
  final String? duePrecision;

  /// The user's own wording, kept so a wrong resolution is auditable (ADR-020).
  final String? dueRawExpression;
  final String priority;
  final DateTime? completedAt;
  final String? assigneeLabel;

  /// An RRULE subset. Present means the task regenerates itself on completion.
  final String? recurrenceRule;
  final DateTime? snoozedUntil;

  bool get isDone => completedAt != null;

  factory TaskDetails.fromJson(Map<String, dynamic> json) => TaskDetails(
        dueAt: parseDate(json['due_at']),
        duePrecision: json['due_precision'] as String?,
        dueRawExpression: json['due_raw_expression'] as String?,
        priority: (json['priority'] as String?) ?? 'normal',
        completedAt: parseDate(json['completed_at']),
        assigneeLabel: json['assignee_label'] as String?,
        recurrenceRule: json['recurrence_rule'] as String?,
        snoozedUntil: parseDate(json['snoozed_until']),
      );
}

class Entry {
  const Entry({
    required this.id,
    required this.type,
    required this.title,
    required this.status,
    required this.occurredAt,
    required this.version,
    this.body,
    this.confidence,
    this.captureId,
    this.task,
    this.tags = const [],
    this.editedByUserAt,
    this.pinnedAt,
    this.projectId,
  });

  final String id;
  final EntryType type;
  final String title;
  final String? body;
  final EntryStatus status;
  final DateTime occurredAt;
  final int version;
  final double? confidence;
  final String? captureId;
  final TaskDetails? task;
  final List<String> tags;
  final DateTime? editedByUserAt;
  final DateTime? pinnedAt;
  final String? projectId;

  bool get needsReview => status == EntryStatus.needsReview;

  factory Entry.fromJson(Map<String, dynamic> json) => Entry(
        id: json['id'] as String,
        type: entryTypeFrom(json['entry_type'] as String?),
        title: (json['title'] as String?) ?? '',
        body: json['body'] as String?,
        status: entryStatusFrom(json['status'] as String?),
        occurredAt: parseDate(json['occurred_at']) ?? DateTime.now(),
        version: (json['version'] as num?)?.toInt() ?? 1,
        confidence: (json['confidence'] as num?)?.toDouble(),
        captureId:
            (json['source'] as Map<String, dynamic>?)?['capture_id'] as String?,
        task: json['task'] == null
            ? null
            : TaskDetails.fromJson(json['task'] as Map<String, dynamic>),
        tags: ((json['tags'] as List<dynamic>?) ?? const []).cast<String>(),
        editedByUserAt: parseDate(json['edited_by_user_at']),
        pinnedAt: parseDate(json['pinned_at']),
        projectId: json['project_id'] as String?,
      );
}

class Transcript {
  const Transcript({
    required this.id,
    required this.text,
    required this.language,
    this.confidence,
  });

  final String id;
  final String text;
  final String language;
  final double? confidence;

  factory Transcript.fromJson(Map<String, dynamic> json) => Transcript(
        id: json['id'] as String,
        text: (json['text'] as String?) ?? '',
        language: (json['language'] as String?) ?? 'fr',
        confidence: (json['confidence'] as num?)?.toDouble(),
      );
}

class Capture {
  const Capture({
    required this.id,
    required this.status,
    required this.durationMs,
    required this.capturedAt,
    this.processingMode = 'normal',
    this.failureCode,
    this.transcript,
    this.audioUrl,
    this.entries = const [],
  });

  final String id;
  final CaptureStatus status;
  final int durationMs;
  final DateTime capturedAt;

  /// `degraded` means the monthly quota was exceeded: the capture is stored and
  /// transcribed, AI enrichment deferred. It is never refused (ADR-026).
  final String processingMode;
  final String? failureCode;
  final Transcript? transcript;
  final String? audioUrl;
  final List<Entry> entries;

  bool get isDegraded => processingMode == 'degraded';

  factory Capture.fromJson(Map<String, dynamic> json) {
    final audio = json['audio'] as Map<String, dynamic>?;
    return Capture(
      id: json['id'] as String,
      status: captureStatusFrom(json['status'] as String?),
      durationMs: (json['duration_ms'] as num?)?.toInt() ?? 0,
      capturedAt: parseDate(json['captured_at']) ?? DateTime.now(),
      processingMode: (json['processing_mode'] as String?) ?? 'normal',
      failureCode: json['failure_code'] as String?,
      transcript: json['transcript'] == null
          ? null
          : Transcript.fromJson(json['transcript'] as Map<String, dynamic>),
      audioUrl: audio?['url'] as String?,
      entries: ((json['entries'] as List<dynamic>?) ?? const [])
          .map((e) => Entry.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}

class DeclaredCapture {
  const DeclaredCapture({
    required this.id,
    required this.uploadUrl,
    required this.uploadHeaders,
    this.quotaWarning,
  });

  final String id;
  final String? uploadUrl;
  final Map<String, String> uploadHeaders;
  final String? quotaWarning;

  factory DeclaredCapture.fromJson(Map<String, dynamic> json) {
    final upload = json['upload'] as Map<String, dynamic>?;
    return DeclaredCapture(
      id: json['id'] as String,
      uploadUrl: upload?['url'] as String?,
      uploadHeaders:
          ((upload?['headers'] as Map<dynamic, dynamic>?) ?? const {}).map(
        (k, v) => MapEntry(k.toString(), v.toString()),
      ),
      quotaWarning: json['quota_warning'] as String?,
    );
  }
}

class Dashboard {
  const Dashboard({
    required this.captureCount,
    required this.entriesByType,
    required this.needsReview,
    required this.dueSoon,
    required this.quota,
  });

  final int captureCount;
  final Map<String, int> entriesByType;
  final int needsReview;
  final List<Entry> dueSoon;
  final Map<String, int?> quota;

  factory Dashboard.fromJson(Map<String, dynamic> json) => Dashboard(
        captureCount: (json['capture_count'] as num?)?.toInt() ?? 0,
        entriesByType:
            ((json['entries_by_type'] as Map<dynamic, dynamic>?) ?? const {})
                .map((k, v) => MapEntry(k.toString(), (v as num).toInt())),
        needsReview: (json['needs_review'] as num?)?.toInt() ?? 0,
        dueSoon: ((json['due_soon'] as List<dynamic>?) ?? const [])
            .map((e) => Entry.fromJson(e as Map<String, dynamic>))
            .toList(),
        quota: ((json['quota'] as Map<dynamic, dynamic>?) ?? const {})
            .map((k, v) => MapEntry(k.toString(), (v as num?)?.toInt())),
      );
}

/// Shared date parsing. Public because the phase-2 models parse the same
/// shapes and duplicating the null-and-local handling is how two files start
/// disagreeing about what a missing date means.
DateTime? parseDate(dynamic value) =>
    value is String ? DateTime.tryParse(value)?.toLocal() : null;
