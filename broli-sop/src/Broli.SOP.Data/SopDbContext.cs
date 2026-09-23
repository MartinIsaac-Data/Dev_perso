using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace Broli.SOP.Data;

/// <summary>
/// Star schema (dimensions + facts) plus operational tables. Provider-agnostic:
/// SQLite for Phase 1, SQL Server by configuration.
/// </summary>
public class SopDbContext(DbContextOptions<SopDbContext> options) : DbContext(options)
{
    // Dimensions
    public DbSet<Country> Countries => Set<Country>();
    public DbSet<Supplier> Suppliers => Set<Supplier>();
    public DbSet<Category> Categories => Set<Category>();
    public DbSet<Brand> Brands => Set<Brand>();
    public DbSet<Product> Products => Set<Product>();
    public DbSet<Agency> Agencies => Set<Agency>();
    public DbSet<Warehouse> Warehouses => Set<Warehouse>();
    public DbSet<Customer> Customers => Set<Customer>();
    public DbSet<DateDim> Dates => Set<DateDim>();

    // Facts
    public DbSet<SalesFact> SalesFacts => Set<SalesFact>();
    public DbSet<InventoryFact> InventoryFacts => Set<InventoryFact>();
    public DbSet<ForecastFact> ForecastFacts => Set<ForecastFact>();
    public DbSet<SupplyLine> SupplyLines => Set<SupplyLine>();
    public DbSet<ProductionFact> ProductionFacts => Set<ProductionFact>();

    // Operational
    public DbSet<RiskItem> RiskItems => Set<RiskItem>();
    public DbSet<AppUser> Users => Set<AppUser>();
    public DbSet<AppRole> Roles => Set<AppRole>();
    public DbSet<UserRole> UserRoles => Set<UserRole>();
    public DbSet<RolePermission> RolePermissions => Set<RolePermission>();
    public DbSet<AuditEntry> AuditEntries => Set<AuditEntry>();
    public DbSet<AppSetting> Settings => Set<AppSetting>();
    public DbSet<ImportBatch> ImportBatches => Set<ImportBatch>();
    public DbSet<SopAction> Actions => Set<SopAction>();
    public DbSet<Notification> Notifications => Set<Notification>();
    public DbSet<AlertState> AlertStates => Set<AlertState>();
    public DbSet<DataSource> DataSources => Set<DataSource>();

    protected override void ConfigureConventions(ModelConfigurationBuilder builder)
    {
        builder.Properties<string>().HaveMaxLength(200);
        // Enums as readable strings: the database stays understandable from SQL / Power BI.
        builder.Properties<MaterialType>().HaveConversion<string>().HaveMaxLength(20);
        builder.Properties<SupplyStatus>().HaveConversion<string>().HaveMaxLength(20);
        builder.Properties<RiskCategory>().HaveConversion<string>().HaveMaxLength(20);
        builder.Properties<RiskStatus>().HaveConversion<string>().HaveMaxLength(20);
        builder.Properties<ImpactLevel>().HaveConversion<string>().HaveMaxLength(20);
        builder.Properties<ImportType>().HaveConversion<string>().HaveMaxLength(20);
        builder.Properties<ImportStatus>().HaveConversion<string>().HaveMaxLength(20);
        builder.Properties<ActionStatus>().HaveConversion<string>().HaveMaxLength(20);
        builder.Properties<ActionPriority>().HaveConversion<string>().HaveMaxLength(20);
        builder.Properties<DataSourceKind>().HaveConversion<string>().HaveMaxLength(20);
    }

    protected override void OnModelCreating(ModelBuilder b)
    {
        b.Entity<Country>(e => { e.ToTable("DIM_COUNTRY"); e.HasIndex(x => x.Code).IsUnique(); e.Property(x => x.Code).HasMaxLength(10); });
        b.Entity<Supplier>(e =>
        {
            e.ToTable("DIM_SUPPLIER");
            e.HasIndex(x => x.Code).IsUnique();
            e.Property(x => x.Code).HasMaxLength(40);
            e.HasOne(x => x.Country).WithMany().HasForeignKey(x => x.CountryId).OnDelete(DeleteBehavior.Restrict);
        });
        b.Entity<Category>(e => { e.ToTable("DIM_CATEGORY"); e.HasIndex(x => x.Code).IsUnique(); e.Property(x => x.Code).HasMaxLength(40); });
        b.Entity<Brand>(e => { e.ToTable("DIM_BRAND"); e.HasIndex(x => x.Name).IsUnique(); e.Property(x => x.Name).HasMaxLength(80); });
        b.Entity<Product>(e =>
        {
            e.ToTable("DIM_PRODUCT");
            e.HasIndex(x => x.CArtSap).IsUnique();
            e.Property(x => x.CArtSap).HasMaxLength(40);
            e.Property(x => x.BaseUnit).HasMaxLength(10);
            e.HasOne(x => x.Category).WithMany().HasForeignKey(x => x.CategoryId).OnDelete(DeleteBehavior.Restrict);
            e.HasOne(x => x.Brand).WithMany().HasForeignKey(x => x.BrandId).OnDelete(DeleteBehavior.Restrict);
            e.HasOne(x => x.MainSupplier).WithMany().HasForeignKey(x => x.MainSupplierId).OnDelete(DeleteBehavior.Restrict);
            e.HasIndex(x => x.CategoryId);
            e.HasIndex(x => x.BrandId);
        });
        b.Entity<Agency>(e => { e.ToTable("DIM_AGENCY"); e.HasIndex(x => x.Code).IsUnique(); e.Property(x => x.Code).HasMaxLength(40); });
        b.Entity<Warehouse>(e => { e.ToTable("DIM_WAREHOUSE"); e.HasIndex(x => x.Code).IsUnique(); e.Property(x => x.Code).HasMaxLength(40); });
        b.Entity<Customer>(e => { e.ToTable("DIM_CUSTOMER"); e.HasIndex(x => x.Code).IsUnique(); e.Property(x => x.Code).HasMaxLength(40); });
        b.Entity<DateDim>(e =>
        {
            e.ToTable("DIM_DATE");
            e.HasKey(x => x.DateKey);
            e.Property(x => x.DateKey).ValueGeneratedNever();
            e.Property(x => x.MonthName).HasMaxLength(20);
        });

        // Facts carry an integer DateKey (yyyymmdd) without a hard FK to DIM_DATE so loads never fail on calendar gaps.
        b.Entity<SalesFact>(e =>
        {
            e.ToTable("FACT_SALES");
            e.HasIndex(x => new { x.DateKey, x.ProductId, x.AgencyId }).IsUnique();
            e.HasIndex(x => new { x.ProductId, x.DateKey });
            Fact(e);
            e.HasOne(x => x.Agency).WithMany().HasForeignKey(x => x.AgencyId).OnDelete(DeleteBehavior.Restrict);
        });
        b.Entity<InventoryFact>(e =>
        {
            e.ToTable("FACT_INVENTORY");
            e.HasIndex(x => new { x.DateKey, x.ProductId, x.WarehouseId }).IsUnique();
            e.HasIndex(x => new { x.ProductId, x.DateKey });
            Fact(e);
            e.HasOne(x => x.Warehouse).WithMany().HasForeignKey(x => x.WarehouseId).OnDelete(DeleteBehavior.Restrict);
        });
        b.Entity<ForecastFact>(e =>
        {
            e.ToTable("FACT_FORECAST");
            e.HasIndex(x => new { x.DateKey, x.ProductId }).IsUnique();
            Fact(e);
        });
        b.Entity<ProductionFact>(e =>
        {
            e.ToTable("FACT_PRODUCTION");
            e.HasIndex(x => new { x.DateKey, x.ProductId }).IsUnique();
            Fact(e);
        });
        b.Entity<SupplyLine>(e =>
        {
            e.ToTable("FACT_SUPPLY");
            e.HasIndex(x => new { x.PoNumber, x.ProductId }).IsUnique();
            e.HasIndex(x => x.Status);
            e.HasIndex(x => x.ActualArrival);
            e.HasIndex(x => x.ProductId);
            e.Property(x => x.PoNumber).HasMaxLength(40);
            e.HasOne(x => x.Product).WithMany().HasForeignKey(x => x.ProductId).OnDelete(DeleteBehavior.Restrict);
            e.HasOne(x => x.Supplier).WithMany().HasForeignKey(x => x.SupplierId).OnDelete(DeleteBehavior.Restrict);
            e.HasOne(x => x.OriginCountry).WithMany().HasForeignKey(x => x.OriginCountryId).OnDelete(DeleteBehavior.Restrict);
        });

        b.Entity<RiskItem>(e =>
        {
            e.ToTable("SOP_RISK");
            e.HasIndex(x => x.Code).IsUnique();
            e.Property(x => x.Code).HasMaxLength(20);
            e.Property(x => x.Description).HasMaxLength(1000);
            e.Property(x => x.Action).HasMaxLength(1000);
            e.HasOne(x => x.Product).WithMany().HasForeignKey(x => x.ProductId).OnDelete(DeleteBehavior.SetNull);
            e.HasOne(x => x.Supplier).WithMany().HasForeignKey(x => x.SupplierId).OnDelete(DeleteBehavior.SetNull);
        });

        b.Entity<AppUser>(e =>
        {
            e.ToTable("SEC_USER");
            e.HasIndex(x => x.Username).IsUnique();
            e.Property(x => x.Username).HasMaxLength(80);
            e.Property(x => x.PasswordHash).HasMaxLength(400);
        });
        b.Entity<AppRole>(e => { e.ToTable("SEC_ROLE"); e.HasIndex(x => x.Name).IsUnique(); e.Property(x => x.Name).HasMaxLength(40); });
        b.Entity<UserRole>(e =>
        {
            e.ToTable("SEC_USER_ROLE");
            e.HasKey(x => new { x.UserId, x.RoleId });
            e.HasOne(x => x.User).WithMany(u => u.Roles).HasForeignKey(x => x.UserId).OnDelete(DeleteBehavior.Cascade);
            e.HasOne(x => x.Role).WithMany().HasForeignKey(x => x.RoleId).OnDelete(DeleteBehavior.Cascade);
        });
        b.Entity<RolePermission>(e =>
        {
            e.ToTable("SEC_ROLE_PERMISSION");
            e.HasKey(x => new { x.RoleId, x.Permission });
            e.Property(x => x.Permission).HasMaxLength(60);
            e.HasOne(x => x.Role).WithMany(r => r.Permissions).HasForeignKey(x => x.RoleId).OnDelete(DeleteBehavior.Cascade);
        });
        b.Entity<AuditEntry>(e =>
        {
            e.ToTable("SYS_AUDIT_LOG");
            e.HasIndex(x => x.TimestampUtc);
            e.Property(x => x.OldValue).HasMaxLength(4000);
            e.Property(x => x.NewValue).HasMaxLength(4000);
        });
        b.Entity<AppSetting>(e =>
        {
            e.ToTable("SYS_SETTING");
            e.HasKey(x => x.Key);
            e.Property(x => x.Key).HasMaxLength(60);
            e.Property(x => x.JsonValue).HasMaxLength(8000);
        });
        b.Entity<ImportBatch>(e =>
        {
            e.ToTable("SYS_IMPORT_BATCH");
            e.HasIndex(x => x.UploadedAtUtc);
            e.Property(x => x.Message).HasMaxLength(2000);
        });
        b.Entity<AppUser>(e =>
        {
            e.Property(x => x.ScopeAgencies).HasMaxLength(1000);
            e.Property(x => x.ScopeCategories).HasMaxLength(1000);
        });
        b.Entity<SopAction>(e =>
        {
            e.ToTable("SOP_ACTION");
            e.HasIndex(x => x.Code).IsUnique();
            e.HasIndex(x => x.Status);
            e.Property(x => x.Code).HasMaxLength(20);
            e.Property(x => x.Description).HasMaxLength(2000);
            e.Property(x => x.Comment).HasMaxLength(2000);
            e.HasOne(x => x.RiskItem).WithMany().HasForeignKey(x => x.RiskItemId).OnDelete(DeleteBehavior.SetNull);
        });
        b.Entity<Notification>(e =>
        {
            e.ToTable("SYS_NOTIFICATION");
            e.HasIndex(x => new { x.UserId, x.ReadAtUtc });
            e.Property(x => x.Message).HasMaxLength(2000);
            e.HasOne<AppUser>().WithMany().HasForeignKey(x => x.UserId).OnDelete(DeleteBehavior.Cascade);
        });
        b.Entity<AlertState>(e =>
        {
            e.ToTable("SYS_ALERT_STATE");
            e.HasKey(x => x.Key);
            e.Property(x => x.Key).HasMaxLength(300);
        });
        b.Entity<DataSource>(e =>
        {
            e.ToTable("SYS_DATA_SOURCE");
            e.HasIndex(x => x.Name).IsUnique();
            e.Property(x => x.Name).HasMaxLength(100);
            e.Property(x => x.DailyAt).HasMaxLength(5);
            e.Property(x => x.LastMessage).HasMaxLength(1000);
        });
    }

    private static void Fact<T>(EntityTypeBuilder<T> e) where T : class
    {
        e.HasIndex("IsDemo");
        e.HasOne(typeof(Product), "Product").WithMany().HasForeignKey("ProductId").OnDelete(DeleteBehavior.Restrict);
    }
}
