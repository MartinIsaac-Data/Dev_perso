using Microsoft.EntityFrameworkCore.Design;

namespace Broli.SOP.Data;

/// <summary>
/// Used only by <c>dotnet ef</c> to generate SQL Server migrations. No connection is opened:
/// the connection string is a placeholder.
/// </summary>
public sealed class SopDbContextFactory : IDesignTimeDbContextFactory<SopDbContext>
{
    public SopDbContext CreateDbContext(string[] args) =>
        new(new DbContextOptionsBuilder<SopDbContext>()
            .UseSqlServer("Server=(design-time);Database=BroliSOP;Trusted_Connection=True;TrustServerCertificate=True")
            .Options);
}
