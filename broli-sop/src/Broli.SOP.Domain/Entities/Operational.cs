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
    public ImportStatus Status { get; set; }
}
