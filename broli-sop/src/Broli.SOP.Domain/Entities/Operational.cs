using Broli.SOP.Domain.Enums;

namespace Broli.SOP.Domain.Entities;

/// <summary>A risk or opportunity tracked in the S&amp;OP register.</summary>
public class RiskItem : IDemoTagged
{
    public int Id { get; set; }
    public string Code { get; set; } = "";
    public RiskCategory Category { get; set; }
    public bool IsOpportunity { get; set; }
    public string Description { get; set; } = "";
    public int? ProductId { get; set; }
    public Product? Product { get; set; }
    public int? SupplierId { get; set; }
    public Supplier? Supplier { get; set; }
    public ImpactLevel Impact { get; set; }
    /// <summary>Probability 0–100 %.</summary>
    public int Probability { get; set; }
    public string Owner { get; set; } = "";
    public string? Action { get; set; }
    public DateOnly? DueDate { get; set; }
    public RiskStatus Status { get; set; } = RiskStatus.Open;
    public DateTime CreatedAtUtc { get; set; }
    public string CreatedBy { get; set; } = "";
    public DateTime? UpdatedAtUtc { get; set; }
    public bool IsDemo { get; set; }
}

public class AppUser
{
    public int Id { get; set; }
    public string Username { get; set; } = "";
    public string DisplayName { get; set; } = "";
    public string? Email { get; set; }
    public string? Department { get; set; }
    public string PasswordHash { get; set; } = "";
    public bool IsActive { get; set; } = true;
    public bool IsDemo { get; set; }
    public int FailedLoginCount { get; set; }
    public DateTime? LockoutEndUtc { get; set; }
    public DateTime? LastLoginUtc { get; set; }
    public DateTime CreatedAtUtc { get; set; }
    /// <summary>Data scope: agency codes this user may see (empty = all). Enforced by the API.</summary>
    public string? ScopeAgencies { get; set; }
    /// <summary>Data scope: product-family codes this user may see (empty = all). Enforced by the API.</summary>
    public string? ScopeCategories { get; set; }
    public List<UserRole> Roles { get; set; } = [];
}

public class AppRole
{
    public int Id { get; set; }
    public string Name { get; set; } = "";
    public string Description { get; set; } = "";
    /// <summary>System roles cannot be deleted (their permissions stay editable).</summary>
    public bool IsSystem { get; set; }
    public List<RolePermission> Permissions { get; set; } = [];
}

public class UserRole
{
    public int UserId { get; set; }
    public AppUser? User { get; set; }
    public int RoleId { get; set; }
    public AppRole? Role { get; set; }
}

public class RolePermission
{
    public int RoleId { get; set; }
    public AppRole? Role { get; set; }
    public string Permission { get; set; } = "";
}

public class AuditEntry
{
    public long Id { get; set; }
    public DateTime TimestampUtc { get; set; }
    public string Username { get; set; } = "";
    public string Action { get; set; } = "";
    public string Module { get; set; } = "";
    public string? ObjectRef { get; set; }
    public string? OldValue { get; set; }
    public string? NewValue { get; set; }
}

/// <summary>A business parameter section, stored as JSON so new parameters need no schema change.</summary>
public class AppSetting
{
    public string Key { get; set; } = "";
    public string JsonValue { get; set; } = "";
    public DateTime UpdatedAtUtc { get; set; }
    public string UpdatedBy { get; set; } = "";
}

public class ImportBatch
{
    public int Id { get; set; }
    public ImportType Type { get; set; }
    public string FileName { get; set; } = "";
    public string UploadedBy { get; set; } = "";
    public DateTime UploadedAtUtc { get; set; }
    public int RowCount { get; set; }
    public int InsertedCount { get; set; }
    public int UpdatedCount { get; set; }
    public int WarningCount { get; set; }
    public int ErrorCount { get; set; }
    public ImportStatus Status { get; set; }
    /// <summary>"Chargement manuel", or the name of the data source for automated refreshes.</summary>
    public string Source { get; set; } = "Chargement manuel";
    /// <summary>Summary of errors for rejected / failed automated runs.</summary>
    public string? Message { get; set; }
}

/// <summary>An S&amp;OP action or decision, owned by a person with a due date.</summary>
public class SopAction : IDemoTagged
{
    public int Id { get; set; }
    public string Code { get; set; } = "";
    public DateOnly Date { get; set; }
    public string Topic { get; set; } = "";
    public string Description { get; set; } = "";
    public string Owner { get; set; } = "";
    public string Department { get; set; } = "";
    public DateOnly? DueDate { get; set; }
    public ActionPriority Priority { get; set; } = ActionPriority.Medium;
    public ActionStatus Status { get; set; } = ActionStatus.Open;
    public string? Comment { get; set; }
    /// <summary>A decision the S&amp;OP meeting must take (shown in the meeting view).</summary>
    public bool IsDecision { get; set; }
    public int? RiskItemId { get; set; }
    public RiskItem? RiskItem { get; set; }
    public string? CArtSap { get; set; }
    public DateTime CreatedAtUtc { get; set; }
    public string CreatedBy { get; set; } = "";
    public DateTime? UpdatedAtUtc { get; set; }
    public string? UpdatedBy { get; set; }
    public bool IsDemo { get; set; }
}

/// <summary>An in-app notification for one user.</summary>
public class Notification
{
    public long Id { get; set; }
    public int UserId { get; set; }
    public DateTime CreatedAtUtc { get; set; }
    public string Kind { get; set; } = "";
    public string Severity { get; set; } = "info";
    public string Title { get; set; } = "";
    public string Message { get; set; } = "";
    public string? Link { get; set; }
    public DateTime? ReadAtUtc { get; set; }
    public bool EmailSent { get; set; }
}

/// <summary>Remembers when an alert was last raised so the same alert is not repeated every run.</summary>
public class AlertState
{
    public string Key { get; set; } = "";
    public DateTime LastRaisedUtc { get; set; }
}

/// <summary>An automated data source feeding the standard import pipeline.</summary>
public class DataSource
{
    public int Id { get; set; }
    public string Name { get; set; } = "";
    public DataSourceKind Kind { get; set; }
    public ImportType ImportType { get; set; }
    /// <summary>ExcelFolder: sub-folder of the configured inbox root. SqlStaging: table or view name.</summary>
    public string Location { get; set; } = "";
    /// <summary>SqlStaging only: name of the connection string in configuration (never the credentials themselves).</summary>
    public string? ConnectionName { get; set; }
    /// <summary>Daily run time "HH:mm" (server local time); null = manual only.</summary>
    public string? DailyAt { get; set; }
    public bool Enabled { get; set; } = true;
    public DateTime? LastRunUtc { get; set; }
    public string? LastStatus { get; set; }
    public string? LastMessage { get; set; }
}

/// <summary>A recurring report the S&amp;OP process expects from a department (reporting catalogue and calendar).</summary>
public class ReportDefinition : IDemoTagged
{
    public int Id { get; set; }
    /// <summary>Reporting ID from the catalogue, e.g. COM-01.</summary>
    public string Code { get; set; } = "";
    public string Department { get; set; } = "";
    public string Name { get; set; } = "";
    /// <summary>Owner / preparer as written in the catalogue; several people are separated by "/".</summary>
    public string Owner { get; set; } = "";
    public string Frequency { get; set; } = "";
    /// <summary>Expected day as written in the catalogue (Friday, Every day, To confirm…).</summary>
    public string ExpectedDay { get; set; } = "";
    public string? ExpectedTime { get; set; }
    public string? MainContent { get; set; }
    /// <summary>Catalogue status (Identified, Received, To Receive…), free text.</summary>
    public string? CatalogueStatus { get; set; }
    public string? Purpose { get; set; }
    public string? FollowUpNotes { get; set; }
    /// <summary>False when the report is no longer in the imported catalogue: kept for history, no longer expected.</summary>
    public bool IsActive { get; set; } = true;
    public bool IsDemo { get; set; }
}

/// <summary>One report for one S&amp;OP week (reporting tracker).</summary>
public class ReportSubmission : IDemoTagged
{
    public int Id { get; set; }
    public int ReportDefinitionId { get; set; }
    public ReportDefinition? Report { get; set; }
    /// <summary>Monday of the S&amp;OP week.</summary>
    public DateOnly WeekStart { get; set; }
    public string WeekLabel { get; set; } = "";
    public DateOnly? ReferenceDate { get; set; }
    public DateOnly? ExpectedDate { get; set; }
    public DateOnly? ReceivedDate { get; set; }
    /// <summary>Status as entered; null lets the portal derive it from the dates.</summary>
    public ReportStatus? Status { get; set; }
    public ReportQuality? Quality { get; set; }
    public bool RelanceRequired { get; set; }
    public string? Comments { get; set; }
    public DateTime? LastReminderUtc { get; set; }
    public bool IsDemo { get; set; }
}
