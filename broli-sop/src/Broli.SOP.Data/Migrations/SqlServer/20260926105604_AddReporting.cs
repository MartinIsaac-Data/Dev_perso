using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Broli.SOP.Data.Migrations.SqlServer
{
    /// <inheritdoc />
    public partial class AddReporting : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "SOP_REPORT_DEFINITION",
                columns: table => new
                {
                    Id = table.Column<int>(type: "int", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    Code = table.Column<string>(type: "nvarchar(40)", maxLength: 40, nullable: false),
                    Department = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    Name = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    Owner = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    Frequency = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    ExpectedDay = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    ExpectedTime = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: true),
                    MainContent = table.Column<string>(type: "nvarchar(1000)", maxLength: 1000, nullable: true),
                    CatalogueStatus = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: true),
                    Purpose = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: true),
                    FollowUpNotes = table.Column<string>(type: "nvarchar(1000)", maxLength: 1000, nullable: true),
                    IsActive = table.Column<bool>(type: "bit", nullable: false),
                    IsDemo = table.Column<bool>(type: "bit", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_SOP_REPORT_DEFINITION", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "SOP_REPORT_SUBMISSION",
                columns: table => new
                {
                    Id = table.Column<int>(type: "int", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    ReportDefinitionId = table.Column<int>(type: "int", nullable: false),
                    WeekStart = table.Column<DateOnly>(type: "date", nullable: false),
                    WeekLabel = table.Column<string>(type: "nvarchar(40)", maxLength: 40, nullable: false),
                    ReferenceDate = table.Column<DateOnly>(type: "date", nullable: true),
                    ExpectedDate = table.Column<DateOnly>(type: "date", nullable: true),
                    ReceivedDate = table.Column<DateOnly>(type: "date", nullable: true),
                    Status = table.Column<string>(type: "nvarchar(20)", maxLength: 20, nullable: true),
                    Quality = table.Column<string>(type: "nvarchar(20)", maxLength: 20, nullable: true),
                    RelanceRequired = table.Column<bool>(type: "bit", nullable: false),
                    Comments = table.Column<string>(type: "nvarchar(1000)", maxLength: 1000, nullable: true),
                    LastReminderUtc = table.Column<DateTime>(type: "datetime2", nullable: true),
                    IsDemo = table.Column<bool>(type: "bit", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_SOP_REPORT_SUBMISSION", x => x.Id);
                    table.ForeignKey(
                        name: "FK_SOP_REPORT_SUBMISSION_SOP_REPORT_DEFINITION_ReportDefinitionId",
                        column: x => x.ReportDefinitionId,
                        principalTable: "SOP_REPORT_DEFINITION",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "IX_SOP_REPORT_DEFINITION_Code",
                table: "SOP_REPORT_DEFINITION",
                column: "Code",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_SOP_REPORT_SUBMISSION_ReportDefinitionId_WeekStart",
                table: "SOP_REPORT_SUBMISSION",
                columns: new[] { "ReportDefinitionId", "WeekStart" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_SOP_REPORT_SUBMISSION_WeekStart",
                table: "SOP_REPORT_SUBMISSION",
                column: "WeekStart");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "SOP_REPORT_SUBMISSION");

            migrationBuilder.DropTable(
                name: "SOP_REPORT_DEFINITION");
        }
    }
}
