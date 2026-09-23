namespace Broli.SOP.Contracts.Security;

/// <summary>
/// Fine-grained permissions. Roles are just named bundles of these, editable by an admin,
/// so new roles can be added without code changes.
/// </summary>
public static class Permissions
{
    public const string ExecutiveView = "executive.view";
    public const string DemandView = "demand.view";
    public const string InventoryView = "inventory.view";
    public const string SupplyView = "supply.view";
    public const string SupplyEdit = "supply.edit";
    public const string RisksView = "risks.view";
    public const string RisksEdit = "risks.edit";
    /// <summary>See costs and stock values. Without it, monetary fields are withheld by the API.</summary>
    public const string FinanceView = "finance.view";
    public const string DataExport = "data.export";
    public const string DataImport = "data.import";
    public const string ConfigEdit = "config.edit";
    public const string UsersManage = "users.manage";
    public const string AuditView = "audit.view";

    public static readonly IReadOnlyList<(string Code, string Description)> All =
    [
        (ExecutiveView, "Executive dashboard"),
        (DemandView, "Demand / Forecast vs Actual"),
        (InventoryView, "Inventory & coverage"),
        (SupplyView, "Supply, open orders, transit"),
        (SupplyEdit, "Edit supply data (ETA, status)"),
        (RisksView, "Risks & opportunities"),
        (RisksEdit, "Create and update risks"),
        (FinanceView, "Financial values (costs, stock value)"),
        (DataExport, "Export tables to Excel / CSV"),
        (DataImport, "Import Excel files, purge demo data"),
        (ConfigEdit, "Edit business configuration"),
        (UsersManage, "Manage users, roles and permissions"),
        (AuditView, "Read the audit log"),
    ];

    /// <summary>Default permission bundles used when the database is first created.</summary>
    public static readonly IReadOnlyDictionary<string, string[]> DefaultRoles = new Dictionary<string, string[]>
    {
        ["ADMIN"] = All.Select(p => p.Code).ToArray(),
        ["MANAGEMENT"] = [ExecutiveView, DemandView, InventoryView, SupplyView, RisksView, RisksEdit, FinanceView, DataExport, AuditView],
        ["SUPPLY"] = [ExecutiveView, DemandView, InventoryView, SupplyView, SupplyEdit, RisksView, RisksEdit, DataExport],
        ["SALES"] = [ExecutiveView, DemandView, InventoryView, RisksView, DataExport],
        ["FINANCE"] = [ExecutiveView, DemandView, InventoryView, SupplyView, RisksView, FinanceView, DataExport],
        ["WAREHOUSE"] = [InventoryView, SupplyView, RisksView, DataExport],
        ["LOGISTICS"] = [SupplyView, InventoryView, RisksView, SupplyEdit, DataExport],
        ["PRODUCTION"] = [DemandView, InventoryView, SupplyView, RisksView, DataExport],
    };
}
