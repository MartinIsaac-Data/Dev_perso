namespace Broli.SOP.Contracts.Dtos;

public record ImportIssue(int Row, string? Column, string Message, string Severity);

public record ImportPreview(
    Guid Id,
    string Type,
    string FileName,
    int RowCount,
    int ValidRowCount,
    IReadOnlyList<string> Columns,
    IReadOnlyList<IReadOnlyDictionary<string, string?>> SampleRows,
    IReadOnlyList<ImportIssue> Issues,
    int ErrorCount,
    int WarningCount,
    bool CanCommit,
    bool WillPurgeDemoData);

public record ImportResult(int BatchId, string Type, int Inserted, int Updated, int Warnings, bool PurgedDemoData);

public record ImportBatchDto(
    int Id,
    string Type,
    string FileName,
    string UploadedBy,
    DateTime UploadedAtUtc,
    int RowCount,
    int Inserted,
    int Updated,
    int Warnings,
    string Status,
    string Source = "Chargement manuel",
    int Errors = 0,
    string? Message = null);

public record ImportTemplateInfo(string Type, string Title, string Description, IReadOnlyList<string> RequiredColumns, IReadOnlyList<string> OptionalColumns);
