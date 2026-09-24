using System.Diagnostics;
using Microsoft.Data.Sqlite;

namespace Broli.SOP.LoadTest;

/// <summary>
/// Bulk-loads a Broli-scale dataset into a database whose schema was created by the API
/// (start the API once on an empty file with Demo:Enabled=false, stop it, then seed).
/// Volumes: <c>skus</c> products over <c>months</c> months, 5 agencies + plant, 3 warehouses, 60 suppliers.
/// </summary>
public static class Seed
{
    public static void Run(string dbPath, int skus, int months, int seed)
    {
        var sw = Stopwatch.StartNew();
        var rnd = new Random(seed);
        using var c = new SqliteConnection($"Data Source={dbPath}");
        c.Open();
        Exec(c, "PRAGMA journal_mode=WAL; PRAGMA synchronous=OFF;");
        using var tx = c.BeginTransaction();

        var today = DateOnly.FromDateTime(DateTime.Today);
        var current = new DateOnly(today.Year, today.Month, 1);
        var start = current.AddMonths(-(months - 1));

        // ---------- Dimensions ----------
        var countries = Query(c, tx, "SELECT Id, Code, DefaultTransitDays FROM DIM_COUNTRY").Select(r => (Id: (long)r[0], Code: (string)r[1], Days: (long)r[2])).ToList();
        string[] catCodes = ["SPAGHETTI", "MACARONI", "SHORT_PASTA", "MAYONNAISE", "BISCUITS", "FILMS", "CARTONS", "JARS_CAPS", "DURUM", "OILS", "INGREDIENTS", "FLOUR"];
        string[] catTypes = ["FinishedGood", "FinishedGood", "FinishedGood", "FinishedGood", "FinishedGood", "Packaging", "Packaging", "Packaging", "RawMaterial", "RawMaterial", "RawMaterial", "RawMaterial"];
        var catIds = new long[catCodes.Length];
        for (var i = 0; i < catCodes.Length; i++)
            catIds[i] = Insert(c, tx, "INSERT INTO DIM_CATEGORY (Code, Name, MaterialType, IsDemo) VALUES ($a,$b,$c,0)", catCodes[i], catCodes[i].Replace('_', ' '), catTypes[i]);
        string[] brands = ["Fiona", "Rahma", "Armanti", "Spaghetto", "Pasta d'Or", "Broli", "Delicia", "Soleil"];
        var brandIds = brands.Select(b => Insert(c, tx, "INSERT INTO DIM_BRAND (Name, IsDemo) VALUES ($a,0)", b)).ToArray();
        var supplierIds = new List<(long Id, long Country, long Days)>();
        for (var i = 1; i <= 60; i++)
        {
            var ct = countries[rnd.Next(countries.Count)];
            supplierIds.Add((Insert(c, tx, "INSERT INTO DIM_SUPPLIER (Code, Name, CountryId, ProductionLeadDays, IsDemo) VALUES ($a,$b,$c,$d,0)",
                $"LT-S{i:000}", $"Load Supplier {i:000}", ct.Id, rnd.Next(7, 30)), ct.Id, ct.Days));
        }
        var agencies = new[] { "DLA", "YDE", "BFS", "GRA", "BTA" }.Select(a => Insert(c, tx, "INSERT INTO DIM_AGENCY (Code, Name, IsInternal, IsDemo) VALUES ($a,$b,0,0)", a, a)).ToArray();
        var plant = Insert(c, tx, "INSERT INTO DIM_AGENCY (Code, Name, IsInternal, IsDemo) VALUES ('PLANT','Plant',1,0)");
        var whMain = Insert(c, tx, "INSERT INTO DIM_WAREHOUSE (Code, Name, IsDemo) VALUES ('WH-DLA','Douala Central',0)");
        var whSecond = Insert(c, tx, "INSERT INTO DIM_WAREHOUSE (Code, Name, IsDemo) VALUES ('WH-YDE','Yaounde DC',0)");
        var whPlant = Insert(c, tx, "INSERT INTO DIM_WAREHOUSE (Code, Name, IsDemo) VALUES ('WH-PLANT','Plant',0)");

        // ---------- Products ----------
        var products = new List<(long Id, bool Fg, double Base, double Cover, (long Id, long Country, long Days) Sup, double PerTc)>();
        var pCmd = Prepare(c, tx, "INSERT INTO DIM_PRODUCT (CArtSap, Description, CategoryId, BrandId, MaterialType, MainSupplierId, BaseUnit, QtyPerTc, UnitCost, IsActive, IsDemo) " +
                                  "VALUES ($a,$b,$c,$d,$e,$f,$g,$h,$i,1,0); SELECT last_insert_rowid();", 9);
        for (var i = 0; i < skus; i++)
        {
            var fg = i < skus / 3;
            var cat = fg ? rnd.Next(0, 5) : rnd.Next(5, catCodes.Length);
            var sup = supplierIds[rnd.Next(supplierIds.Count)];
            var unit = fg ? "CTN" : cat is 6 or 7 ? "UNIT" : "KG";
            var perTc = fg ? 2400.0 : unit == "UNIT" ? 60000 : 25000;
            var id = (long)Exec(pCmd, $"LT{100000 + i}", $"{catCodes[cat]} ITEM {i:00000}", catIds[cat], fg || cat == 5 ? brandIds[rnd.Next(brandIds.Length)] : null,
                catTypes[cat], fg ? null : sup.Id, unit, perTc, Math.Round(100 + rnd.NextDouble() * 9000))!;
            var baseDemand = fg ? 200 + rnd.NextDouble() * 3000 : unit == "KG" ? 1000 + rnd.NextDouble() * 60000 : 5000 + rnd.NextDouble() * 50000;
            var cover = rnd.NextDouble() switch { < 0.1 => 0.5, < 0.3 => 1.5, < 0.85 => 3.5, _ => 8 };
            products.Add((id, fg, baseDemand, cover, sup, perTc));
        }

        // ---------- Facts ----------
        var sales = Prepare(c, tx, "INSERT INTO FACT_SALES (DateKey, ProductId, AgencyId, ForecastQty, ActualQty, OrderedQty, IsDemo) VALUES ($a,$b,$c,$d,$e,$f,0)", 6);
        var inv = Prepare(c, tx, "INSERT INTO FACT_INVENTORY (DateKey, ProductId, WarehouseId, StockQty, IsDemo) VALUES ($a,$b,$c,$d,0)", 4);
        var fc = Prepare(c, tx, "INSERT INTO FACT_FORECAST (DateKey, ProductId, ForecastQty, IsDemo) VALUES ($a,$b,$c,0)", 3);
        var prod = Prepare(c, tx, "INSERT INTO FACT_PRODUCTION (DateKey, ProductId, PlannedQty, ProducedQty, IsDemo) VALUES ($a,$b,$c,$d,0)", 4);
        var sup2 = Prepare(c, tx, "INSERT INTO FACT_SUPPLY (PoNumber, ProductId, SupplierId, OriginCountryId, Quantity, DeliveredQty, Containers, OrderDate, RequiredDate, Etd, Eta, ActualArrival, Status, Port, IsDemo) " +
                                  "VALUES ($a,$b,$c,$d,$e,$f,$g,$h,$i,$j,$k,$l,$m,'Douala',0)", 13);
        long rows = 0, po = 46000000;
        double[] season = [0, .95, .94, 1.1, 1.12, 1, .95, .9, .88, 1, 1.03, 1.06, 1.2];
        static int Key(DateOnly d) => d.Year * 10000 + d.Month * 100 + d.Day;
        static string D(DateOnly d) => d.ToString("yyyy-MM-dd");

        foreach (var p in products)
        {
            var stock = p.Base * p.Cover;
            for (var m = start; m <= current; m = m.AddMonths(1))
            {
                var demand = p.Base * season[m.Month] * (0.85 + rnd.NextDouble() * 0.3);
                var mk = Key(m);
                if (p.Fg)
                {
                    foreach (var a in agencies)
                    {
                        var share = demand / agencies.Length * (0.8 + rnd.NextDouble() * 0.4);
                        Exec(sales, mk, p.Id, a, Math.Round(share * (0.9 + rnd.NextDouble() * 0.25)), Math.Round(share * 0.98), Math.Round(share));
                        rows++;
                    }
                    var produced = Math.Max(0, demand + (p.Cover * p.Base - stock) * 0.5);
                    Exec(prod, mk, p.Id, Math.Round(produced * 1.05), Math.Round(produced)); rows++;
                    stock = Math.Max(0, stock + produced - demand);
                    var end = m == current ? today : m.AddMonths(1).AddDays(-1);
                    Exec(inv, Key(end), p.Id, whMain, Math.Round(stock * 0.6)); Exec(inv, Key(end), p.Id, whSecond, Math.Round(stock * 0.4)); rows += 2;
                }
                else
                {
                    Exec(sales, mk, p.Id, plant, Math.Round(demand * (0.9 + rnd.NextDouble() * 0.25)), Math.Round(demand), null); rows++;
                    // One PO per month when below target: delivered in the past, open around today.
                    if (stock < p.Base * p.Cover)
                    {
                        var qty = Math.Ceiling(Math.Max(p.Base * p.Cover - stock + demand, p.PerTc / 4) / 1000) * 1000;
                        var order = m.AddDays(rnd.Next(0, 20));
                        var etd = order.AddDays(15);
                        var eta = etd.AddDays((int)p.Sup.Days);
                        var late = rnd.NextDouble() < 0.25 ? rnd.Next(3, 25) : 0;
                        var arrival = eta.AddDays(late);
                        var delivered = arrival <= today;
                        var status = delivered ? "Delivered" : today < etd ? "InProduction" : today < eta ? "Shipped" : "AtPort";
                        Exec(sup2, (po++).ToString(), p.Id, p.Sup.Id, p.Sup.Country, qty, delivered ? qty : null, Math.Ceiling(qty / p.PerTc),
                            D(order), D(eta.AddDays(3)), D(etd), D(delivered ? eta : arrival), delivered ? D(arrival) : null, status);
                        rows++;
                        if (delivered) stock += qty;
                    }
                    stock = Math.Max(0, stock - demand);
                    var end = m == current ? today : m.AddMonths(1).AddDays(-1);
                    Exec(inv, Key(end), p.Id, whPlant, Math.Round(stock)); rows++;
                }
            }
            for (var i = 0; i <= 6; i++) { Exec(fc, Key(current.AddMonths(i)), p.Id, Math.Round(p.Base * season[current.AddMonths(i).Month])); rows++; }
        }

        // Register and action plan at a busy company's scale.
        for (var i = 1; i <= 200; i++)
            Exec(c, tx, "INSERT INTO SOP_RISK (Code, Category, IsOpportunity, Description, ProductId, Impact, Probability, Owner, DueDate, Status, CreatedAtUtc, CreatedBy, IsDemo) " +
                        "VALUES ($a,'Stockout',0,'Load test risk',$b,'High',50,'Supply',$c,'Open',$d,'load',0)", $"R-{i:0000}", products[rnd.Next(products.Count)].Id, D(today.AddDays(rnd.Next(-20, 40))), DateTime.UtcNow.ToString("O"));
        for (var i = 1; i <= 500; i++)
            Exec(c, tx, "INSERT INTO SOP_ACTION (Code, Date, Topic, Description, Owner, Department, DueDate, Priority, Status, IsDecision, CreatedAtUtc, CreatedBy, IsDemo) " +
                        "VALUES ($a,$b,'Load','Load test action','Supply Planner','Supply Chain',$c,'Medium',$d,$e,$f,'load',0)",
                $"A-{i:0000}", D(today.AddDays(-rnd.Next(1, 90))), D(today.AddDays(rnd.Next(-20, 40))), i % 4 == 0 ? "Done" : "Open", i % 10 == 0 ? 1 : 0, DateTime.UtcNow.ToString("O"));
        Exec(c, tx, "INSERT INTO SYS_IMPORT_BATCH (Type, FileName, UploadedBy, UploadedAtUtc, RowCount, InsertedCount, UpdatedCount, WarningCount, ErrorCount, Status, Source) " +
                    "VALUES ('Inventory','load-test','load',$a,$b,$b,0,0,0,'Committed','Load test')", DateTime.UtcNow.ToString("O"), rows);
        tx.Commit();
        Exec(c, "ANALYZE;");
        Console.WriteLine($"Seeded {skus:N0} SKUs over {months} months: {rows:N0} fact rows in {sw.Elapsed.TotalSeconds:0.0} s");
    }

    private static void Exec(SqliteConnection c, string sql) { using var cmd = c.CreateCommand(); cmd.CommandText = sql; cmd.ExecuteNonQuery(); }

    private static void Exec(SqliteConnection c, SqliteTransaction tx, string sql, params object?[] args)
    {
        using var cmd = c.CreateCommand();
        cmd.Transaction = tx;
        cmd.CommandText = sql;
        for (var i = 0; i < args.Length; i++) cmd.Parameters.AddWithValue("$" + (char)('a' + i), args[i] ?? DBNull.Value);
        cmd.ExecuteNonQuery();
    }

    private static long Insert(SqliteConnection c, SqliteTransaction tx, string sql, params object?[] args)
    {
        using var cmd = c.CreateCommand();
        cmd.Transaction = tx;
        cmd.CommandText = sql + "; SELECT last_insert_rowid();";
        for (var i = 0; i < args.Length; i++) cmd.Parameters.AddWithValue("$" + (char)('a' + i), args[i] ?? DBNull.Value);
        return (long)cmd.ExecuteScalar()!;
    }

    private static List<object[]> Query(SqliteConnection c, SqliteTransaction tx, string sql)
    {
        using var cmd = c.CreateCommand();
        cmd.Transaction = tx;
        cmd.CommandText = sql;
        using var r = cmd.ExecuteReader();
        var list = new List<object[]>();
        while (r.Read()) { var v = new object[r.FieldCount]; r.GetValues(v); list.Add(v); }
        return list;
    }

    private static SqliteCommand Prepare(SqliteConnection c, SqliteTransaction tx, string sql, int parameters)
    {
        var cmd = c.CreateCommand();
        cmd.Transaction = tx;
        cmd.CommandText = sql;
        for (var i = 0; i < parameters; i++) cmd.Parameters.Add(new SqliteParameter("$" + (char)('a' + i), null));
        cmd.Prepare();
        return cmd;
    }

    private static object? Exec(SqliteCommand cmd, params object?[] values)
    {
        for (var i = 0; i < values.Length; i++) cmd.Parameters[i].Value = values[i] ?? DBNull.Value;
        return cmd.ExecuteScalar();
    }
}
