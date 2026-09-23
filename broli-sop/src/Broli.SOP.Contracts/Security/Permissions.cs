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
    public const string ActionsView = "actions.view";
    /// <summary>Create and update S&amp;OP actions and decisions.</summary>
    public const string ActionsEdit = "actions.edit";

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
        (ActionsView, "S&OP action plan and meeting view"),
        (ActionsEdit, "Create and update S&OP actions"),
    ];

    /// <summary>Default permission bundles used when the database is first created.</summary>
    public static readonly IReadOnlyDictionary<string, string[]> DefaultRoles = new Dictionary<string, string[]>
    {
        ["ADMIN"] = All.Select(p => p.Code).ToArray(),
        ["MANAGEMENT"] = [ExecutiveView, DemandView, InventoryView, SupplyView, RisksView, RisksEdit, FinanceView, DataExport, AuditView, ActionsView, ActionsEdit],
        ["SUPPLY"] = [ExecutiveView, DemandView, InventoryView, SupplyView, SupplyEdit, RisksView, RisksEdit, DataExport, ActionsView, ActionsEdit],
        ["SALES"] = [ExecutiveView, DemandView, InventoryView, RisksView, DataExport, ActionsView, ActionsEdit],
        ["FINANCE"] = [ExecutiveView, DemandView, InventoryView, SupplyView, RisksView, FinanceView, DataExport, ActionsView],
        ["WAREHOUSE"] = [InventoryView, SupplyView, RisksView, DataExport, ActionsView],
        ["LOGISTICS"] = [SupplyView, InventoryView, RisksView, SupplyEdit, DataExport, ActionsView, ActionsEdit],
        ["PRODUCTION"] = [DemandView, InventoryView, SupplyView, RisksView, DataExport, ActionsView, ActionsEdit],
    };
}
