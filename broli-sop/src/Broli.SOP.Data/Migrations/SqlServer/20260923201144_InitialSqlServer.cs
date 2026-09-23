using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Broli.SOP.Data.Migrations.SqlServer
{
    /// <inheritdoc />
    public partial class InitialSqlServer : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "DIM_AGENCY",
                columns: table => new
                {
                    Id = table.Column<int>(type: "int", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    Code = table.Column<string>(type: "nvarchar(40)", maxLength: 40, nullable: false),
                    Name = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    IsInternal = table.Column<bool>(type: "bit", nullable: false),
                    IsDemo = table.Column<bool>(type: "bit", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_DIM_AGENCY", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "DIM_BRAND",
                columns: table => new
                {
                    Id = table.Column<int>(type: "int", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    Name = table.Column<string>(type: "nvarchar(80)", maxLength: 80, nullable: false),
                    IsDemo = table.Column<bool>(type: "bit", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_DIM_BRAND", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "DIM_CATEGORY",
                columns: table => new
                {
                    Id = table.Column<int>(type: "int", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    Code = table.Column<string>(type: "nvarchar(40)", maxLength: 40, nullable: false),
                    Name = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    MaterialType = table.Column<string>(type: "nvarchar(20)", maxLength: 20, nullable: false),
                    IsDemo = table.Column<bool>(type: "bit", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_DIM_CATEGORY", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "DIM_COUNTRY",
                columns: table => new
                {
                    Id = table.Column<int>(type: "int", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    Code = table.Column<string>(type: "nvarchar(10)", maxLength: 10, nullable: false),
                    Name = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    DefaultTransitDays = table.Column<int>(type: "int", nullable: false),
                    IsDemo = table.Column<bool>(type: "bit", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_DIM_COUNTRY", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "DIM_CUSTOMER",
                columns: table => new
                {
                    Id = table.Column<int>(type: "int", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    Code = table.Column<string>(type: "nvarchar(40)", maxLength: 40, nullable: false),
                    Name = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    AgencyId = table.Column<int>(type: "int", nullable: true),
                    IsDemo = table.Column<bool>(type: "bit", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_DIM_CUSTOMER", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "DIM_DATE",
                columns: table => new
                {
                    DateKey = table.Column<int>(type: "int", nullable: false),
                    Date = table.Column<DateOnly>(type: "date", nullable: false),
                    Year = table.Column<int>(type: "int", nullable: false),
                    Quarter = table.Column<int>(type: "int", nullable: false),
                    Month = table.Column<int>(type: "int", nullable: false),
                    MonthName = table.Column<string>(type: "nvarchar(20)", maxLength: 20, nullable: false),
                    FiscalYear = table.Column<int>(type: "int", nullable: false),
                    FiscalPeriod = table.Column<int>(type: "int", nullable: false),
                    IsMonthStart = table.Column<bool>(type: "bit", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_DIM_DATE", x => x.DateKey);
                });

            migrationBuilder.CreateTable(
                name: "DIM_WAREHOUSE",
                columns: table => new
                {
                    Id = table.Column<int>(type: "int", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    Code = table.Column<string>(type: "nvarchar(40)", maxLength: 40, nullable: false),
                    Name = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    IsDemo = table.Column<bool>(type: "bit", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_DIM_WAREHOUSE", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "SEC_ROLE",
                columns: table => new
                {
                    Id = table.Column<int>(type: "int", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    Name = table.Column<string>(type: "nvarchar(40)", maxLength: 40, nullable: false),
                    Description = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    IsSystem = table.Column<bool>(type: "bit", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_SEC_ROLE", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "SEC_USER",
                columns: table => new
                {
                    Id = table.Column<int>(type: "int", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    Username = table.Column<string>(type: "nvarchar(80)", maxLength: 80, nullable: false),
                    DisplayName = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    Email = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: true),
                    Department = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: true),
                    PasswordHash = table.Column<string>(type: "nvarchar(400)", maxLength: 400, nullable: false),
                    IsActive = table.Column<bool>(type: "bit", nullable: false),
                    IsDemo = table.Column<bool>(type: "bit", nullable: false),
                    FailedLoginCount = table.Column<int>(type: "int", nullable: false),
                    LockoutEndUtc = table.Column<DateTime>(type: "datetime2", nullable: true),
                    LastLoginUtc = table.Column<DateTime>(type: "datetime2", nullable: true),
                    CreatedAtUtc = table.Column<DateTime>(type: "datetime2", nullable: false),
                    ScopeAgencies = table.Column<string>(type: "nvarchar(1000)", maxLength: 1000, nullable: true),
                    ScopeCategories = table.Column<string>(type: "nvarchar(1000)", maxLength: 1000, nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_SEC_USER", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "SYS_ALERT_STATE",
                columns: table => new
                {
                    Key = table.Column<string>(type: "nvarchar(300)", maxLength: 300, nullable: false),
                    LastRaisedUtc = table.Column<DateTime>(type: "datetime2", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_SYS_ALERT_STATE", x => x.Key);
                });

            migrationBuilder.CreateTable(
                name: "SYS_AUDIT_LOG",
                columns: table => new
                {
                    Id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    TimestampUtc = table.Column<DateTime>(type: "datetime2", nullable: false),
                    Username = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    Action = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    Module = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    ObjectRef = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: true),
                    OldValue = table.Column<string>(type: "nvarchar(4000)", maxLength: 4000, nullable: true),
                    NewValue = table.Column<string>(type: "nvarchar(4000)", maxLength: 4000, nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_SYS_AUDIT_LOG", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "SYS_DATA_SOURCE",
                columns: table => new
                {
                    Id = table.Column<int>(type: "int", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    Name = table.Column<string>(type: "nvarchar(100)", maxLength: 100, nullable: false),
                    Kind = table.Column<string>(type: "nvarchar(20)", maxLength: 20, nullable: false),
                    ImportType = table.Column<string>(type: "nvarchar(20)", maxLength: 20, nullable: false),
                    Location = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    ConnectionName = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: true),
                    DailyAt = table.Column<string>(type: "nvarchar(5)", maxLength: 5, nullable: true),
                    Enabled = table.Column<bool>(type: "bit", nullable: false),
                    LastRunUtc = table.Column<DateTime>(type: "datetime2", nullable: true),
                    LastStatus = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: true),
                    LastMessage = table.Column<string>(type: "nvarchar(1000)", maxLength: 1000, nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_SYS_DATA_SOURCE", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "SYS_IMPORT_BATCH",
                columns: table => new
                {
                    Id = table.Column<int>(type: "int", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    Type = table.Column<string>(type: "nvarchar(20)", maxLength: 20, nullable: false),
                    FileName = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    UploadedBy = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    UploadedAtUtc = table.Column<DateTime>(type: "datetime2", nullable: false),
                    RowCount = table.Column<int>(type: "int", nullable: false),
                    InsertedCount = table.Column<int>(type: "int", nullable: false),
                    UpdatedCount = table.Column<int>(type: "int", nullable: false),
                    WarningCount = table.Column<int>(type: "int", nullable: false),
                    ErrorCount = table.Column<int>(type: "int", nullable: false),
                    Status = table.Column<string>(type: "nvarchar(20)", maxLength: 20, nullable: false),
                    Source = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    Message = table.Column<string>(type: "nvarchar(2000)", maxLength: 2000, nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_SYS_IMPORT_BATCH", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "SYS_SETTING",
                columns: table => new
                {
                    Key = table.Column<string>(type: "nvarchar(60)", maxLength: 60, nullable: false),
                    JsonValue = table.Column<string>(type: "nvarchar(max)", maxLength: 8000, nullable: false),
                    UpdatedAtUtc = table.Column<DateTime>(type: "datetime2", nullable: false),
                    UpdatedBy = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_SYS_SETTING", x => x.Key);
                });

            migrationBuilder.CreateTable(
                name: "DIM_SUPPLIER",
                columns: table => new
                {
                    Id = table.Column<int>(type: "int", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    Code = table.Column<string>(type: "nvarchar(40)", maxLength: 40, nullable: false),
                    Name = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    CountryId = table.Column<int>(type: "int", nullable: false),
                    TransitDays = table.Column<int>(type: "int", nullable: true),
                    ProductionLeadDays = table.Column<int>(type: "int", nullable: false),
                    IsDemo = table.Column<bool>(type: "bit", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_DIM_SUPPLIER", x => x.Id);
                    table.ForeignKey(
                        name: "FK_DIM_SUPPLIER_DIM_COUNTRY_CountryId",
                        column: x => x.CountryId,
                        principalTable: "DIM_COUNTRY",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "SEC_ROLE_PERMISSION",
                columns: table => new
                {
                    RoleId = table.Column<int>(type: "int", nullable: false),
                    Permission = table.Column<string>(type: "nvarchar(60)", maxLength: 60, nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_SEC_ROLE_PERMISSION", x => new { x.RoleId, x.Permission });
                    table.ForeignKey(
                        name: "FK_SEC_ROLE_PERMISSION_SEC_ROLE_RoleId",
                        column: x => x.RoleId,
                        principalTable: "SEC_ROLE",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "SEC_USER_ROLE",
                columns: table => new
                {
                    UserId = table.Column<int>(type: "int", nullable: false),
                    RoleId = table.Column<int>(type: "int", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_SEC_USER_ROLE", x => new { x.UserId, x.RoleId });
                    table.ForeignKey(
                        name: "FK_SEC_USER_ROLE_SEC_ROLE_RoleId",
                        column: x => x.RoleId,
                        principalTable: "SEC_ROLE",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                    table.ForeignKey(
                        name: "FK_SEC_USER_ROLE_SEC_USER_UserId",
                        column: x => x.UserId,
                        principalTable: "SEC_USER",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "SYS_NOTIFICATION",
                columns: table => new
                {
                    Id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    UserId = table.Column<int>(type: "int", nullable: false),
                    CreatedAtUtc = table.Column<DateTime>(type: "datetime2", nullable: false),
                    Kind = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    Severity = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    Title = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    Message = table.Column<string>(type: "nvarchar(2000)", maxLength: 2000, nullable: false),
                    Link = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: true),
                    ReadAtUtc = table.Column<DateTime>(type: "datetime2", nullable: true),
                    EmailSent = table.Column<bool>(type: "bit", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_SYS_NOTIFICATION", x => x.Id);
                    table.ForeignKey(
                        name: "FK_SYS_NOTIFICATION_SEC_USER_UserId",
                        column: x => x.UserId,
                        principalTable: "SEC_USER",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "DIM_PRODUCT",
                columns: table => new
                {
                    Id = table.Column<int>(type: "int", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    CArtSap = table.Column<string>(type: "nvarchar(40)", maxLength: 40, nullable: false),
                    Description = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    CategoryId = table.Column<int>(type: "int", nullable: false),
                    BrandId = table.Column<int>(type: "int", nullable: true),
                    MaterialType = table.Column<string>(type: "nvarchar(20)", maxLength: 20, nullable: false),
                    MainSupplierId = table.Column<int>(type: "int", nullable: true),
                    BaseUnit = table.Column<string>(type: "nvarchar(10)", maxLength: 10, nullable: false),
                    UnitWeightKg = table.Column<double>(type: "float", nullable: true),
                    Colisage = table.Column<double>(type: "float", nullable: true),
                    QtyPerTc = table.Column<double>(type: "float", nullable: true),
                    UnitCost = table.Column<double>(type: "float", nullable: true),
                    SafetyStockQty = table.Column<double>(type: "float", nullable: true),
                    Format = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: true),
                    Color = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: true),
                    IsActive = table.Column<bool>(type: "bit", nullable: false),
                    IsDemo = table.Column<bool>(type: "bit", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_DIM_PRODUCT", x => x.Id);
                    table.ForeignKey(
                        name: "FK_DIM_PRODUCT_DIM_BRAND_BrandId",
                        column: x => x.BrandId,
                        principalTable: "DIM_BRAND",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                    table.ForeignKey(
                        name: "FK_DIM_PRODUCT_DIM_CATEGORY_CategoryId",
                        column: x => x.CategoryId,
                        principalTable: "DIM_CATEGORY",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                    table.ForeignKey(
                        name: "FK_DIM_PRODUCT_DIM_SUPPLIER_MainSupplierId",
                        column: x => x.MainSupplierId,
                        principalTable: "DIM_SUPPLIER",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "FACT_FORECAST",
                columns: table => new
                {
                    Id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    DateKey = table.Column<int>(type: "int", nullable: false),
                    ProductId = table.Column<int>(type: "int", nullable: false),
                    ForecastQty = table.Column<double>(type: "float", nullable: false),
                    ImportBatchId = table.Column<int>(type: "int", nullable: true),
                    IsDemo = table.Column<bool>(type: "bit", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_FACT_FORECAST", x => x.Id);
                    table.ForeignKey(
                        name: "FK_FACT_FORECAST_DIM_PRODUCT_ProductId",
                        column: x => x.ProductId,
                        principalTable: "DIM_PRODUCT",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "FACT_INVENTORY",
                columns: table => new
                {
                    Id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    DateKey = table.Column<int>(type: "int", nullable: false),
                    ProductId = table.Column<int>(type: "int", nullable: false),
                    WarehouseId = table.Column<int>(type: "int", nullable: false),
                    StockQty = table.Column<double>(type: "float", nullable: false),
                    ImportBatchId = table.Column<int>(type: "int", nullable: true),
                    IsDemo = table.Column<bool>(type: "bit", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_FACT_INVENTORY", x => x.Id);
                    table.ForeignKey(
                        name: "FK_FACT_INVENTORY_DIM_PRODUCT_ProductId",
                        column: x => x.ProductId,
                        principalTable: "DIM_PRODUCT",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                    table.ForeignKey(
                        name: "FK_FACT_INVENTORY_DIM_WAREHOUSE_WarehouseId",
                        column: x => x.WarehouseId,
                        principalTable: "DIM_WAREHOUSE",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "FACT_PRODUCTION",
                columns: table => new
                {
                    Id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    DateKey = table.Column<int>(type: "int", nullable: false),
                    ProductId = table.Column<int>(type: "int", nullable: false),
                    PlannedQty = table.Column<double>(type: "float", nullable: false),
                    ProducedQty = table.Column<double>(type: "float", nullable: false),
                    ImportBatchId = table.Column<int>(type: "int", nullable: true),
                    IsDemo = table.Column<bool>(type: "bit", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_FACT_PRODUCTION", x => x.Id);
                    table.ForeignKey(
                        name: "FK_FACT_PRODUCTION_DIM_PRODUCT_ProductId",
                        column: x => x.ProductId,
                        principalTable: "DIM_PRODUCT",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "FACT_SALES",
                columns: table => new
                {
                    Id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    DateKey = table.Column<int>(type: "int", nullable: false),
                    ProductId = table.Column<int>(type: "int", nullable: false),
                    AgencyId = table.Column<int>(type: "int", nullable: false),
                    ForecastQty = table.Column<double>(type: "float", nullable: false),
                    ActualQty = table.Column<double>(type: "float", nullable: false),
                    OrderedQty = table.Column<double>(type: "float", nullable: true),
                    ImportBatchId = table.Column<int>(type: "int", nullable: true),
                    IsDemo = table.Column<bool>(type: "bit", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_FACT_SALES", x => x.Id);
                    table.ForeignKey(
                        name: "FK_FACT_SALES_DIM_AGENCY_AgencyId",
                        column: x => x.AgencyId,
                        principalTable: "DIM_AGENCY",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                    table.ForeignKey(
                        name: "FK_FACT_SALES_DIM_PRODUCT_ProductId",
                        column: x => x.ProductId,
                        principalTable: "DIM_PRODUCT",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "FACT_SUPPLY",
                columns: table => new
                {
                    Id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    PoNumber = table.Column<string>(type: "nvarchar(40)", maxLength: 40, nullable: false),
                    ProductId = table.Column<int>(type: "int", nullable: false),
                    SupplierId = table.Column<int>(type: "int", nullable: false),
                    OriginCountryId = table.Column<int>(type: "int", nullable: true),
                    Quantity = table.Column<double>(type: "float", nullable: false),
                    DeliveredQty = table.Column<double>(type: "float", nullable: true),
                    Containers = table.Column<double>(type: "float", nullable: true),
                    OrderDate = table.Column<DateOnly>(type: "date", nullable: false),
                    RequiredDate = table.Column<DateOnly>(type: "date", nullable: true),
                    Etd = table.Column<DateOnly>(type: "date", nullable: true),
                    Eta = table.Column<DateOnly>(type: "date", nullable: true),
                    ActualArrival = table.Column<DateOnly>(type: "date", nullable: true),
                    Status = table.Column<string>(type: "nvarchar(20)", maxLength: 20, nullable: false),
                    Port = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: true),
                    Booking = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: true),
                    BillOfLading = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: true),
                    CustomsStatus = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: true),
                    ImportBatchId = table.Column<int>(type: "int", nullable: true),
                    IsDemo = table.Column<bool>(type: "bit", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_FACT_SUPPLY", x => x.Id);
                    table.ForeignKey(
                        name: "FK_FACT_SUPPLY_DIM_COUNTRY_OriginCountryId",
                        column: x => x.OriginCountryId,
                        principalTable: "DIM_COUNTRY",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                    table.ForeignKey(
                        name: "FK_FACT_SUPPLY_DIM_PRODUCT_ProductId",
                        column: x => x.ProductId,
                        principalTable: "DIM_PRODUCT",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                    table.ForeignKey(
                        name: "FK_FACT_SUPPLY_DIM_SUPPLIER_SupplierId",
                        column: x => x.SupplierId,
                        principalTable: "DIM_SUPPLIER",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "SOP_RISK",
                columns: table => new
                {
                    Id = table.Column<int>(type: "int", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    Code = table.Column<string>(type: "nvarchar(20)", maxLength: 20, nullable: false),
                    Category = table.Column<string>(type: "nvarchar(20)", maxLength: 20, nullable: false),
                    IsOpportunity = table.Column<bool>(type: "bit", nullable: false),
                    Description = table.Column<string>(type: "nvarchar(1000)", maxLength: 1000, nullable: false),
                    ProductId = table.Column<int>(type: "int", nullable: true),
                    SupplierId = table.Column<int>(type: "int", nullable: true),
                    Impact = table.Column<string>(type: "nvarchar(20)", maxLength: 20, nullable: false),
                    Probability = table.Column<int>(type: "int", nullable: false),
                    Owner = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    Action = table.Column<string>(type: "nvarchar(1000)", maxLength: 1000, nullable: true),
                    DueDate = table.Column<DateOnly>(type: "date", nullable: true),
                    Status = table.Column<string>(type: "nvarchar(20)", maxLength: 20, nullable: false),
                    CreatedAtUtc = table.Column<DateTime>(type: "datetime2", nullable: false),
                    CreatedBy = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    UpdatedAtUtc = table.Column<DateTime>(type: "datetime2", nullable: true),
                    IsDemo = table.Column<bool>(type: "bit", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_SOP_RISK", x => x.Id);
                    table.ForeignKey(
                        name: "FK_SOP_RISK_DIM_PRODUCT_ProductId",
                        column: x => x.ProductId,
                        principalTable: "DIM_PRODUCT",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.SetNull);
                    table.ForeignKey(
                        name: "FK_SOP_RISK_DIM_SUPPLIER_SupplierId",
                        column: x => x.SupplierId,
                        principalTable: "DIM_SUPPLIER",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.SetNull);
                });

            migrationBuilder.CreateTable(
                name: "SOP_ACTION",
                columns: table => new
                {
                    Id = table.Column<int>(type: "int", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    Code = table.Column<string>(type: "nvarchar(20)", maxLength: 20, nullable: false),
                    Date = table.Column<DateOnly>(type: "date", nullable: false),
                    Topic = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    Description = table.Column<string>(type: "nvarchar(2000)", maxLength: 2000, nullable: false),
                    Owner = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    Department = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    DueDate = table.Column<DateOnly>(type: "date", nullable: true),
                    Priority = table.Column<string>(type: "nvarchar(20)", maxLength: 20, nullable: false),
                    Status = table.Column<string>(type: "nvarchar(20)", maxLength: 20, nullable: false),
                    Comment = table.Column<string>(type: "nvarchar(2000)", maxLength: 2000, nullable: true),
                    IsDecision = table.Column<bool>(type: "bit", nullable: false),
                    RiskItemId = table.Column<int>(type: "int", nullable: true),
                    CArtSap = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: true),
                    CreatedAtUtc = table.Column<DateTime>(type: "datetime2", nullable: false),
                    CreatedBy = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    UpdatedAtUtc = table.Column<DateTime>(type: "datetime2", nullable: true),
                    UpdatedBy = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: true),
                    IsDemo = table.Column<bool>(type: "bit", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_SOP_ACTION", x => x.Id);
                    table.ForeignKey(
                        name: "FK_SOP_ACTION_SOP_RISK_RiskItemId",
                        column: x => x.RiskItemId,
                        principalTable: "SOP_RISK",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.SetNull);
                });

            migrationBuilder.CreateIndex(
                name: "IX_DIM_AGENCY_Code",
                table: "DIM_AGENCY",
                column: "Code",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_DIM_BRAND_Name",
                table: "DIM_BRAND",
                column: "Name",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_DIM_CATEGORY_Code",
                table: "DIM_CATEGORY",
                column: "Code",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_DIM_COUNTRY_Code",
                table: "DIM_COUNTRY",
                column: "Code",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_DIM_CUSTOMER_Code",
                table: "DIM_CUSTOMER",
                column: "Code",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_DIM_PRODUCT_BrandId",
                table: "DIM_PRODUCT",
                column: "BrandId");

            migrationBuilder.CreateIndex(
                name: "IX_DIM_PRODUCT_CArtSap",
                table: "DIM_PRODUCT",
                column: "CArtSap",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_DIM_PRODUCT_CategoryId",
                table: "DIM_PRODUCT",
                column: "CategoryId");

            migrationBuilder.CreateIndex(
                name: "IX_DIM_PRODUCT_MainSupplierId",
                table: "DIM_PRODUCT",
                column: "MainSupplierId");

            migrationBuilder.CreateIndex(
                name: "IX_DIM_SUPPLIER_Code",
                table: "DIM_SUPPLIER",
                column: "Code",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_DIM_SUPPLIER_CountryId",
                table: "DIM_SUPPLIER",
                column: "CountryId");

            migrationBuilder.CreateIndex(
                name: "IX_DIM_WAREHOUSE_Code",
                table: "DIM_WAREHOUSE",
                column: "Code",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_FACT_FORECAST_DateKey_ProductId",
                table: "FACT_FORECAST",
                columns: new[] { "DateKey", "ProductId" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_FACT_FORECAST_IsDemo",
                table: "FACT_FORECAST",
                column: "IsDemo");

            migrationBuilder.CreateIndex(
                name: "IX_FACT_FORECAST_ProductId",
                table: "FACT_FORECAST",
                column: "ProductId");

            migrationBuilder.CreateIndex(
                name: "IX_FACT_INVENTORY_DateKey_ProductId_WarehouseId",
                table: "FACT_INVENTORY",
                columns: new[] { "DateKey", "ProductId", "WarehouseId" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_FACT_INVENTORY_IsDemo",
                table: "FACT_INVENTORY",
                column: "IsDemo");

            migrationBuilder.CreateIndex(
                name: "IX_FACT_INVENTORY_ProductId_DateKey",
                table: "FACT_INVENTORY",
                columns: new[] { "ProductId", "DateKey" });

            migrationBuilder.CreateIndex(
                name: "IX_FACT_INVENTORY_WarehouseId",
                table: "FACT_INVENTORY",
                column: "WarehouseId");

            migrationBuilder.CreateIndex(
                name: "IX_FACT_PRODUCTION_DateKey_ProductId",
                table: "FACT_PRODUCTION",
                columns: new[] { "DateKey", "ProductId" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_FACT_PRODUCTION_IsDemo",
                table: "FACT_PRODUCTION",
                column: "IsDemo");

            migrationBuilder.CreateIndex(
                name: "IX_FACT_PRODUCTION_ProductId",
                table: "FACT_PRODUCTION",
                column: "ProductId");

            migrationBuilder.CreateIndex(
                name: "IX_FACT_SALES_AgencyId",
                table: "FACT_SALES",
                column: "AgencyId");

            migrationBuilder.CreateIndex(
                name: "IX_FACT_SALES_DateKey_ProductId_AgencyId",
                table: "FACT_SALES",
                columns: new[] { "DateKey", "ProductId", "AgencyId" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_FACT_SALES_IsDemo",
                table: "FACT_SALES",
                column: "IsDemo");

            migrationBuilder.CreateIndex(
                name: "IX_FACT_SALES_ProductId_DateKey",
                table: "FACT_SALES",
                columns: new[] { "ProductId", "DateKey" });

            migrationBuilder.CreateIndex(
                name: "IX_FACT_SUPPLY_ActualArrival",
                table: "FACT_SUPPLY",
                column: "ActualArrival");

            migrationBuilder.CreateIndex(
                name: "IX_FACT_SUPPLY_OriginCountryId",
                table: "FACT_SUPPLY",
                column: "OriginCountryId");

            migrationBuilder.CreateIndex(
                name: "IX_FACT_SUPPLY_PoNumber_ProductId",
                table: "FACT_SUPPLY",
                columns: new[] { "PoNumber", "ProductId" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_FACT_SUPPLY_ProductId",
                table: "FACT_SUPPLY",
                column: "ProductId");

            migrationBuilder.CreateIndex(
                name: "IX_FACT_SUPPLY_Status",
                table: "FACT_SUPPLY",
                column: "Status");

            migrationBuilder.CreateIndex(
                name: "IX_FACT_SUPPLY_SupplierId",
                table: "FACT_SUPPLY",
                column: "SupplierId");

            migrationBuilder.CreateIndex(
                name: "IX_SEC_ROLE_Name",
                table: "SEC_ROLE",
                column: "Name",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_SEC_USER_Username",
                table: "SEC_USER",
                column: "Username",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_SEC_USER_ROLE_RoleId",
                table: "SEC_USER_ROLE",
                column: "RoleId");

            migrationBuilder.CreateIndex(
                name: "IX_SOP_ACTION_Code",
                table: "SOP_ACTION",
                column: "Code",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_SOP_ACTION_RiskItemId",
                table: "SOP_ACTION",
                column: "RiskItemId");

            migrationBuilder.CreateIndex(
                name: "IX_SOP_ACTION_Status",
                table: "SOP_ACTION",
                column: "Status");

            migrationBuilder.CreateIndex(
                name: "IX_SOP_RISK_Code",
                table: "SOP_RISK",
                column: "Code",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_SOP_RISK_ProductId",
                table: "SOP_RISK",
                column: "ProductId");

            migrationBuilder.CreateIndex(
                name: "IX_SOP_RISK_SupplierId",
                table: "SOP_RISK",
                column: "SupplierId");

            migrationBuilder.CreateIndex(
                name: "IX_SYS_AUDIT_LOG_TimestampUtc",
                table: "SYS_AUDIT_LOG",
                column: "TimestampUtc");

            migrationBuilder.CreateIndex(
                name: "IX_SYS_DATA_SOURCE_Name",
                table: "SYS_DATA_SOURCE",
                column: "Name",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_SYS_IMPORT_BATCH_UploadedAtUtc",
                table: "SYS_IMPORT_BATCH",
                column: "UploadedAtUtc");

            migrationBuilder.CreateIndex(
                name: "IX_SYS_NOTIFICATION_UserId_ReadAtUtc",
                table: "SYS_NOTIFICATION",
                columns: new[] { "UserId", "ReadAtUtc" });
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "DIM_CUSTOMER");

            migrationBuilder.DropTable(
                name: "DIM_DATE");

            migrationBuilder.DropTable(
                name: "FACT_FORECAST");

            migrationBuilder.DropTable(
                name: "FACT_INVENTORY");

            migrationBuilder.DropTable(
                name: "FACT_PRODUCTION");

            migrationBuilder.DropTable(
                name: "FACT_SALES");

            migrationBuilder.DropTable(
                name: "FACT_SUPPLY");

            migrationBuilder.DropTable(
                name: "SEC_ROLE_PERMISSION");

            migrationBuilder.DropTable(
                name: "SEC_USER_ROLE");

            migrationBuilder.DropTable(
                name: "SOP_ACTION");

            migrationBuilder.DropTable(
                name: "SYS_ALERT_STATE");

            migrationBuilder.DropTable(
                name: "SYS_AUDIT_LOG");

            migrationBuilder.DropTable(
                name: "SYS_DATA_SOURCE");

            migrationBuilder.DropTable(
                name: "SYS_IMPORT_BATCH");

            migrationBuilder.DropTable(
                name: "SYS_NOTIFICATION");

            migrationBuilder.DropTable(
                name: "SYS_SETTING");

            migrationBuilder.DropTable(
                name: "DIM_WAREHOUSE");

            migrationBuilder.DropTable(
                name: "DIM_AGENCY");

            migrationBuilder.DropTable(
                name: "SEC_ROLE");

            migrationBuilder.DropTable(
                name: "SOP_RISK");

            migrationBuilder.DropTable(
                name: "SEC_USER");

            migrationBuilder.DropTable(
                name: "DIM_PRODUCT");

            migrationBuilder.DropTable(
                name: "DIM_BRAND");

            migrationBuilder.DropTable(
                name: "DIM_CATEGORY");

            migrationBuilder.DropTable(
                name: "DIM_SUPPLIER");

            migrationBuilder.DropTable(
                name: "DIM_COUNTRY");
        }
    }
}
