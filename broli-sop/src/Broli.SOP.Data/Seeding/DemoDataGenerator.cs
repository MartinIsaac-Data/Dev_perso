namespace Broli.SOP.Data.Seeding;

/// <summary>
/// Generates a realistic, internally consistent DEMO dataset (every row flagged IsDemo, codes prefixed "DM"/"DEMO-").
/// Purchased items are simulated day by day with a reorder policy, so stock, receipts, consumption and
/// purchase orders reconcile exactly; finished goods are simulated monthly from production.
/// Profiles (healthy, tight, critical, excess, dormant) guarantee every risk situation is represented.
/// </summary>
public sealed class DemoDataGenerator(SopDbContext db, IClock clock, int seed)
{
    private enum Profile { Healthy, Tight, Critical, Excess, Dormant }

    private sealed class Spec
    {
        public required Product Product { get; init; }
        public required double BaseMonthly { get; init; }
        public required Profile Profile { get; set; }
        public double Bias { get; init; }
        public double Growth { get; init; }
        public Supplier? Supplier { get; init; }
        public double TargetMonths { get; set; }
    }

    private readonly Random _rnd = new(seed);
    private DateOnly _today;
    private DateOnly _currentMonth;
    private DateOnly _simStart;
    private int _poSeq = 45000100;

    private static readonly double[] Season = [0, 0.95, 0.94, 1.1, 1.12, 1.0, 0.95, 0.9, 0.88, 1.0, 1.03, 1.06, 1.2];
    private static readonly (string Code, string Name, double Share)[] AgencySpecs =
    [
        ("DLA", "Douala", 0.35), ("YDE", "Yaoundé", 0.28), ("BFS", "Bafoussam", 0.14), ("GRA", "Garoua", 0.13), ("BTA", "Bertoua", 0.10),
    ];

    public async Task GenerateAsync(CancellationToken ct)
    {
        _today = clock.Today;
        _currentMonth = DateKeys.MonthStart(_today);
        _simStart = _currentMonth.AddMonths(-13);
        db.ChangeTracker.AutoDetectChangesEnabled = false;

        var countries = await db.Countries.ToDictionaryAsync(c => c.Code, ct);

        // ---------- Dimensions ----------
        var suppliers = new Dictionary<string, Supplier>();
        (string Key, string Name, string Country, int Lead)[] supplierSpecs =
        [
            ("S01", "Anatolia Films Ltd", "TR", 20), ("S02", "Guangzhou FlexPack Co", "CN", 25), ("S03", "Milano Packaging SpA", "IT", 18),
            ("S04", "Kuala Poly Films Bhd", "MY", 22), ("S05", "Ege Flexible Ambalaj", "TR", 20), ("S06", "Canadian Durum Traders", "CA", 12),
            ("S07", "Black Sea Grain LLC", "UA", 10), ("S08", "Mediterranea Semolina", "IT", 10), ("S09", "Kazakh Grain Export", "KZ", 14),
            ("S10", "Palm Oil Malaysia Bhd", "MY", 12), ("S11", "Soja Brasil Óleos", "BR", 12), ("S12", "Ovo Ingredients BV", "NL", 15),
            ("S13", "Dijon Moutarde SA", "FR", 12), ("S14", "Vinaigrerie Ibérica", "ES", 10), ("S15", "Cartonnerie du Littoral", "CM", 7),
            ("S16", "Verrerie Atlas", "MA", 20), ("S17", "Capsules Delta", "EG", 18), ("S18", "Sel & Épices Douala", "CM", 3),
            ("S19", "Indo Spice Exports", "IN", 15), ("S20", "Label Print Nigeria", "NG", 10),
        ];
        foreach (var s in supplierSpecs)
        {
            var sup = new Supplier { Code = $"DEMO-{s.Key}", Name = s.Name, CountryId = countries[s.Country].Id, ProductionLeadDays = s.Lead, IsDemo = true };
            suppliers[s.Key] = sup;
            db.Suppliers.Add(sup);
        }

        var cats = new Dictionary<string, Category>();
        foreach (var (code, name, type) in new[]
                 {
                     ("SPAGHETTI", "Spaghetti", MaterialType.FinishedGood), ("MACARONI", "Macaroni", MaterialType.FinishedGood),
                     ("SHORT_PASTA", "Pâtes courtes", MaterialType.FinishedGood), ("MAYONNAISE", "Mayonnaise", MaterialType.FinishedGood),
                     ("FILMS", "Films", MaterialType.Packaging), ("CARTONS", "Cartons", MaterialType.Packaging),
                     ("JARS_CAPS", "Bocaux, capsules et étiquettes", MaterialType.Packaging), ("DURUM", "Blé dur et semoule", MaterialType.RawMaterial),
                     ("OILS", "Huiles", MaterialType.RawMaterial), ("INGREDIENTS", "Ingrédients", MaterialType.RawMaterial),
                 })
        {
            cats[code] = new Category { Code = code, Name = name, MaterialType = type, IsDemo = true };
            db.Categories.Add(cats[code]);
        }

        var brandNames = new[] { "Fiona", "Rahma", "Armanti", "Spaghetto", "Pasta d'Or" };
        var brands = brandNames.ToDictionary(n => n, n => new Brand { Name = n, IsDemo = true });
        db.Brands.AddRange(brands.Values);

        var agencies = AgencySpecs.Select(a => new Agency { Code = a.Code, Name = a.Name, IsDemo = true }).ToList();
        var plant = new Agency { Code = "PLANT", Name = "Usine (consommation interne)", IsInternal = true, IsDemo = true };
        db.Agencies.AddRange(agencies);
        db.Agencies.Add(plant);

        var whDouala = new Warehouse { Code = "WH-DLA", Name = "Douala Central", IsDemo = true };
        var whYaounde = new Warehouse { Code = "WH-YDE", Name = "Yaoundé DC", IsDemo = true };
        var whPlant = new Warehouse { Code = "WH-PLANT", Name = "Usine MP et emballages", IsDemo = true };
        db.Warehouses.AddRange(whDouala, whYaounde, whPlant);

        for (var i = 1; i <= 10; i++)
            db.Customers.Add(new Customer { Code = $"DEMO-C{i:00}", Name = $"Distributeur démo {i:00}", IsDemo = true });

        db.ChangeTracker.DetectChanges();
        await db.SaveChangesAsync(ct);
        var agencyShares = agencies.Zip(AgencySpecs, (a, s) => (Agency: a, s.Share)).ToList();

        // ---------- Products ----------
        var specs = new List<Spec>();
        var seq = 100;
        Product NewProduct(string category, string description, Brand? brand, string unit, double? perTc, double cost, double? weight = null,
            double? colisage = null, Supplier? supplier = null, string? format = null, string? color = null)
        {
            var c = cats[category];
            var p = new Product
            {
                CArtSap = $"DM{(int)c.MaterialType}{++seq:00000}", Description = description, CategoryId = c.Id, BrandId = brand?.Id,
                MaterialType = c.MaterialType, MainSupplierId = supplier?.Id, BaseUnit = unit, QtyPerTc = perTc, UnitCost = cost,
                UnitWeightKg = weight, Colisage = colisage, Format = format, Color = color, IsDemo = true,
            };
            db.Products.Add(p);
            return p;
        }
        Profile RandomProfile()
        {
            var x = _rnd.NextDouble();
            return x < 0.60 ? Profile.Healthy : x < 0.77 ? Profile.Tight : x < 0.84 ? Profile.Critical : x < 0.96 ? Profile.Excess : Profile.Dormant;
        }
        void Add(Product p, double baseMonthly, Supplier? s, Profile? profile = null) => specs.Add(new Spec
        {
            Product = p, BaseMonthly = baseMonthly, Supplier = s, Profile = profile ?? RandomProfile(),
            Bias = Math.Round(_rnd.NextDouble() * 0.35 - 0.15, 3), Growth = _rnd.NextDouble() < 0.12 ? 0.45 : _rnd.NextDouble() * 0.1 - 0.03,
        });

        var colors = new Dictionary<string, string> { ["Fiona"] = "Rouge", ["Rahma"] = "Vert", ["Armanti"] = "Bleu", ["Spaghetto"] = "Jaune", ["Pasta d'Or"] = "Or" };
        var pastaItems = new (string Cat, string Name, string Format, double Weight, double Colisage, double Volume)[]
        {
            ("SPAGHETTI", "Spaghetti", "500g", 0.5, 20, 2400), ("SPAGHETTI", "Spaghetti", "1kg", 1, 10, 1500),
            ("MACARONI", "Macaroni", "500g", 0.5, 20, 1500), ("MACARONI", "Macaroni", "1kg", 1, 10, 700),
            ("SHORT_PASTA", "Penne", "500g", 0.5, 20, 900), ("SHORT_PASTA", "Coquillettes", "500g", 0.5, 20, 800),
            ("SHORT_PASTA", "Fusilli", "500g", 0.5, 20, 600), ("SHORT_PASTA", "Vermicelli", "200g", 0.2, 40, 1100),
        };
        var brandWeight = new Dictionary<string, double> { ["Fiona"] = 1.3, ["Rahma"] = 1.1, ["Armanti"] = 0.8, ["Spaghetto"] = 0.9, ["Pasta d'Or"] = 0.6 };
        foreach (var b in brandNames)
            foreach (var it in pastaItems)
            {
                var p = NewProduct(it.Cat, $"{it.Name.ToUpperInvariant()} {b.ToUpperInvariant()} {it.Format.ToUpperInvariant()}", brands[b], "CTN",
                    Math.Round(24000 / (it.Weight * it.Colisage)), Math.Round(it.Weight * it.Colisage * 780), it.Weight, it.Colisage, null, it.Format);
                Add(p, Math.Round(it.Volume * brandWeight[b] * (0.8 + _rnd.NextDouble() * 0.4)), null);
            }
        foreach (var (b, fmt, vol) in new[] { ("Fiona", "250ml", 900.0), ("Fiona", "500ml", 1300.0), ("Fiona", "1L", 500.0), ("Rahma", "500ml", 700.0) })
            Add(NewProduct("MAYONNAISE", $"MAYONNAISE {b.ToUpperInvariant()} {fmt.ToUpperInvariant()}", brands[b], "CTN", 1800, 14500, null, 12, null, fmt),
                vol, null, b == "Fiona" && fmt == "500ml" ? Profile.Tight : null);

        // Films: the Rahma films carry the scripted scenario (critical items with late shipments).
        var filmSuppliers = new[] { suppliers["S01"], suppliers["S02"], suppliers["S03"], suppliers["S04"], suppliers["S05"] };
        var filmFormats = new (string Name, string Format, double Kg)[]
        {
            ("SPAGHETTI", "500g", 9000), ("SPAGHETTI", "1kg", 5500), ("MACARONI", "500g", 5800), ("MACARONI", "1kg", 3000),
            ("SHORT PASTA", "500g", 7000), ("FUSILLI", "500g", 2400), ("VERMICELLI", "200g", 3600),
        };
        var fi = 0;
        foreach (var b in brandNames)
            foreach (var f in filmFormats)
            {
                var sup = filmSuppliers[fi++ % filmSuppliers.Length];
                if (b == "Rahma") sup = f.Name is "SPAGHETTI" or "MACARONI" ? suppliers["S01"] : suppliers["S02"];
                var p = NewProduct("FILMS", $"FILM {b.ToUpperInvariant()} {f.Name} {f.Format.ToUpperInvariant()}", brands[b], "KG", 18000, 2600, null, null, sup, f.Format, colors[b]);
                Profile? profile = b != "Rahma" ? null : (f.Name, f.Format) switch
                {
                    ("SPAGHETTI", "500g") => Profile.Critical,
                    ("MACARONI", "500g") => Profile.Critical,
                    ("VERMICELLI", _) => Profile.Tight,
                    ("SHORT PASTA", _) => Profile.Excess,
                    _ => Profile.Healthy,
                };
                Add(p, Math.Round(f.Kg * brandWeight[b] * (0.8 + _rnd.NextDouble() * 0.4)), sup, profile);
            }
        Add(NewProduct("FILMS", "FILM NEUTRE TRANSPARENT 500G", null, "KG", 18000, 2300, null, null, suppliers["S04"], "500g", "Clear"), 4000, suppliers["S04"]);
        Add(NewProduct("FILMS", "FILM NEUTRE IMPRIME PROMO", null, "KG", 18000, 2450, null, null, suppliers["S05"], "500g", "White"), 1500, suppliers["S05"], Profile.Dormant);

        var local = suppliers["S15"];
        Add(NewProduct("CARTONS", "CARTON 20X500G", null, "UNIT", 60000, 310, null, null, local), 48000, local);
        Add(NewProduct("CARTONS", "CARTON 10X1KG", null, "UNIT", 60000, 290, null, null, local), 26000, local);
        Add(NewProduct("CARTONS", "CARTON 40X200G", null, "UNIT", 60000, 270, null, null, local), 9000, local);
        Add(NewProduct("CARTONS", "CARTON MAYONNAISE 12", null, "UNIT", 60000, 330, null, null, local), 3200, local);
        Add(NewProduct("JARS_CAPS", "BOCAL VERRE 250ML", null, "UNIT", 45000, 95, null, null, suppliers["S16"]), 11000, suppliers["S16"]);
        Add(NewProduct("JARS_CAPS", "BOCAL VERRE 500ML", null, "UNIT", 36000, 120, null, null, suppliers["S16"]), 16000, suppliers["S16"], Profile.Tight);
        Add(NewProduct("JARS_CAPS", "BOCAL VERRE 1L", null, "UNIT", 22000, 160, null, null, suppliers["S16"]), 6000, suppliers["S16"]);
        Add(NewProduct("JARS_CAPS", "CAPSULE TWIST-OFF 63MM", null, "UNIT", 400000, 22, null, null, suppliers["S17"]), 27000, suppliers["S17"]);
        Add(NewProduct("JARS_CAPS", "CAPSULE TWIST-OFF 82MM", null, "UNIT", 300000, 26, null, null, suppliers["S17"]), 6000, suppliers["S17"]);
        Add(NewProduct("JARS_CAPS", "ETIQUETTE MAYONNAISE FIONA", null, "UNIT", 2000000, 6, null, null, suppliers["S20"]), 30000, suppliers["S20"]);
        Add(NewProduct("DURUM", "BLE DUR CANADA CWAD", null, "KG", null, 310, null, null, suppliers["S06"]), 950000, suppliers["S06"]);
        Add(NewProduct("DURUM", "BLE DUR UKRAINE", null, "KG", null, 285, null, null, suppliers["S07"]), 620000, suppliers["S07"], Profile.Critical);
        Add(NewProduct("DURUM", "BLE DUR KAZAKHSTAN", null, "KG", null, 290, null, null, suppliers["S09"]), 400000, suppliers["S09"]);
        Add(NewProduct("DURUM", "SEMOULE SSSE PREMIUM", null, "KG", null, 420, null, null, suppliers["S08"]), 180000, suppliers["S08"]);
        Add(NewProduct("OILS", "HUILE DE SOJA RAFFINEE", null, "KG", 22000, 1150, null, null, suppliers["S11"]), 42000, suppliers["S11"]);
        Add(NewProduct("OILS", "OLEINE DE PALME", null, "KG", 22000, 980, null, null, suppliers["S10"]), 30000, suppliers["S10"]);
        Add(NewProduct("OILS", "HUILE DE TOURNESOL", null, "KG", 22000, 1250, null, null, suppliers["S07"]), 12000, suppliers["S07"]);
        Add(NewProduct("INGREDIENTS", "JAUNE D'OEUF EN POUDRE", null, "KG", 12000, 5200, null, null, suppliers["S12"]), 2600, suppliers["S12"], Profile.Tight);
        Add(NewProduct("INGREDIENTS", "PATE DE MOUTARDE", null, "KG", 15000, 2100, null, null, suppliers["S13"]), 1800, suppliers["S13"]);
        Add(NewProduct("INGREDIENTS", "VINAIGRE D'ALCOOL 10%", null, "KG", 20000, 650, null, null, suppliers["S14"]), 3500, suppliers["S14"]);
        Add(NewProduct("INGREDIENTS", "SEL RAFFINE", null, "KG", null, 120, null, null, suppliers["S18"]), 5000, suppliers["S18"]);
        Add(NewProduct("INGREDIENTS", "SUCRE SEMOULE", null, "KG", null, 700, null, null, suppliers["S18"]), 2500, suppliers["S18"]);
        Add(NewProduct("INGREDIENTS", "MELANGE EPICES MAYO", null, "KG", 10000, 4800, null, null, suppliers["S19"]), 300, suppliers["S19"], Profile.Excess);
        Add(NewProduct("INGREDIENTS", "GOMME XANTHANE", null, "KG", 10000, 7400, null, null, suppliers["S12"]), 250, suppliers["S12"]);

        db.ChangeTracker.DetectChanges();
        await db.SaveChangesAsync(ct);

        foreach (var s in specs)
            s.TargetMonths = s.Profile switch
            {
                // Coverage is measured on the (seasonally higher, biased) forecast, so targets sit above the bands they aim for.
                Profile.Healthy => 3.9 + _rnd.NextDouble() * 1.4,
                Profile.Tight => 2.0 + _rnd.NextDouble() * 0.7,
                Profile.Critical => 0.5 + _rnd.NextDouble() * 0.3,
                Profile.Excess => 8.0 + _rnd.NextDouble() * 3,
                _ => 3 + _rnd.NextDouble() * 2,
            };

        // ---------- Facts ----------
        foreach (var s in specs)
        {
            if (s.Product.MaterialType == MaterialType.FinishedGood) SimulateFinishedGood(s, agencyShares, whDouala, whYaounde);
            else SimulatePurchased(s, plant, whPlant, countries.Values.ToDictionary(c => c.Id));
            AddForwardForecast(s);
        }
        db.ChangeTracker.DetectChanges();
        await db.SaveChangesAsync(ct);

        AddRiskRegister(specs, suppliers);
        db.ChangeTracker.DetectChanges();
        await db.SaveChangesAsync(ct);
        AddActions(specs);
        db.ChangeTracker.DetectChanges();
        await db.SaveChangesAsync(ct);
        AddReporting();
        db.ChangeTracker.DetectChanges();
        await db.SaveChangesAsync(ct);
        db.ChangeTracker.AutoDetectChangesEnabled = true;
        db.ChangeTracker.Clear();
    }

    private double Noise(double spread) => 1 + (_rnd.NextDouble() * 2 - 1) * spread;

    /// <summary>Underlying monthly demand for a product (full month).</summary>
    private double Demand(Spec s, DateOnly month)
    {
        var monthsFromNow = (month.Year - _currentMonth.Year) * 12 + month.Month - _currentMonth.Month;
        if (s.Profile == Profile.Dormant && monthsFromNow > -4) return 0;
        var trend = 1 + s.Growth * (monthsFromNow + 13) / 13.0;
        return Math.Max(0, s.BaseMonthly * Season[month.Month] * trend);
    }

    private double MonthFraction(DateOnly month) =>
        month == _currentMonth ? (double)_today.Day / DateTime.DaysInMonth(month.Year, month.Month) : 1.0;

    private void SimulateFinishedGood(Spec s, List<(Agency Agency, double Share)> agencies, Warehouse main, Warehouse second)
    {
        var p = s.Product;
        var stock = Demand(s, _simStart) * s.TargetMonths;
        for (var m = _simStart; m <= _currentMonth; m = m.AddMonths(1))
        {
            var frac = MonthFraction(m);
            var key = DateKeys.MonthKey(m);
            var demand = Demand(s, m) * Noise(0.1) * frac;
            var nextDemand = Demand(s, m.AddMonths(1));
            var planned = Math.Max(0, demand + (s.TargetMonths * nextDemand - stock) * 0.6 * frac);
            var efficiency = s.Profile == Profile.Critical && m == _currentMonth ? 0.6 : 0.9 + _rnd.NextDouble() * 0.14;
            var produced = Math.Round(planned * efficiency);
            db.ProductionFacts.Add(new ProductionFact { DateKey = key, ProductId = p.Id, PlannedQty = Math.Round(planned), ProducedQty = produced, IsDemo = true });

            var available = stock + produced;
            var sold = Math.Min(demand, available);
            foreach (var (agency, share) in agencies)
            {
                var agencyDemand = demand * share * Noise(0.08);
                var actual = Math.Round(demand > 0 ? agencyDemand * sold / demand : 0);
                var forecast = Math.Round(agencyDemand * (1 + s.Bias) * Noise(0.12));
                var ordered = Math.Round(agencyDemand * (1 + _rnd.NextDouble() * 0.03));
                db.SalesFacts.Add(new SalesFact
                {
                    DateKey = key, ProductId = p.Id, AgencyId = agency.Id, ForecastQty = forecast, ActualQty = Math.Min(actual, ordered),
                    OrderedQty = ordered, IsDemo = true,
                });
            }
            stock = Math.Max(0, available - sold);
            var snapshot = m == _currentMonth ? _today : DateKeys.MonthEnd(m);
            var first = Math.Round(stock * 0.65);
            db.InventoryFacts.Add(new InventoryFact { DateKey = DateKeys.ToKey(snapshot), ProductId = p.Id, WarehouseId = main.Id, StockQty = first, IsDemo = true });
            db.InventoryFacts.Add(new InventoryFact { DateKey = DateKeys.ToKey(snapshot), ProductId = p.Id, WarehouseId = second.Id, StockQty = Math.Round(stock) - first, IsDemo = true });
        }
    }

    private sealed class Po
    {
        public required SupplyLine Line { get; init; }
        public DateOnly Arrival { get; init; }
        public DateOnly PlannedEta { get; init; }
        public DateOnly RevisedEtd { get; init; }
        public bool Delivered { get; set; }
    }

    private void SimulatePurchased(Spec s, Agency plant, Warehouse wh, Dictionary<int, Country> countriesById)
    {
        var p = s.Product;
        var sup = s.Supplier!;
        var country = countriesById[sup.CountryId];
        var isLocal = country.Code == "CM";
        var transit = country.DefaultTransitDays;
        var lead = sup.ProductionLeadDays + transit;
        var perTc = p.QtyPerTc ?? 25000;
        var multiple = s.BaseMonthly >= perTc / 2 ? perTc : Math.Max(100, Math.Round(s.BaseMonthly / 4 / 100) * 100);

        var stock = Demand(s, _simStart) * s.TargetMonths;
        var pipeline = new List<Po>();
        var consumed = new Dictionary<DateOnly, double>();
        var wanted = new Dictionary<DateOnly, double>();
        var daily = 0.0;
        var month = DateOnly.MinValue;

        for (var d = _simStart; d <= _today; d = d.AddDays(1))
        {
            var m = DateKeys.MonthStart(d);
            if (m != month)
            {
                month = m;
                daily = Demand(s, m) * Noise(0.08) / DateTime.DaysInMonth(m.Year, m.Month);
            }

            foreach (var po in pipeline.Where(x => !x.Delivered && x.Arrival == d))
            {
                po.Delivered = true;
                stock += po.Line.Quantity;
            }

            var want = daily * Noise(0.25);
            var got = Math.Min(want, stock);
            stock -= got;
            consumed[m] = consumed.GetValueOrDefault(m) + got;
            wanted[m] = wanted.GetValueOrDefault(m) + want;

            if (d.DayOfWeek == DayOfWeek.Monday && d < _today.AddDays(-2))
            {
                var avg = Demand(s, m);
                var position = stock + pipeline.Where(x => !x.Delivered).Sum(x => x.Line.Quantity);
                var reorderPoint = avg * (lead / 30.0 + s.TargetMonths * 0.75);
                if (avg > 0 && position < reorderPoint)
                {
                    var qty = KpiRound(avg * (s.TargetMonths + lead / 30.0) - position, multiple);
                    pipeline.Add(NewPo(p, sup, country, isLocal, d, qty, perTc));
                }
            }

            if (d == DateKeys.MonthEnd(m) || d == _today)
                db.InventoryFacts.Add(new InventoryFact { DateKey = DateKeys.ToKey(d), ProductId = p.Id, WarehouseId = wh.Id, StockQty = Math.Round(stock), IsDemo = true });
        }

        foreach (var (m, got) in consumed)
        {
            var forecastFull = Demand(s, m) * (1 + s.Bias) * Noise(0.1);
            db.SalesFacts.Add(new SalesFact
            {
                DateKey = DateKeys.MonthKey(m), ProductId = p.Id, AgencyId = plant.Id,
                ForecastQty = Math.Round(forecastFull * MonthFraction(m)), ActualQty = Math.Round(got), IsDemo = true,
            });
        }

        // Scripted situation for critical items: the only inbound shipment arrives after the projected stockout.
        if (s.Profile == Profile.Critical)
        {
            pipeline.RemoveAll(x => !x.Delivered);
            var dailyNow = Demand(s, _currentMonth) / DateTime.DaysInMonth(_today.Year, _today.Month);
            var daysLeft = dailyNow > 0 ? (int)(stock / dailyNow) : 30;
            var etd = _today.AddDays(-Math.Min(10, transit / 2));
            var eta = _today.AddDays(daysLeft + 12 + _rnd.Next(0, 8));
            var line = new SupplyLine
            {
                PoNumber = (_poSeq++).ToString(), ProductId = p.Id, SupplierId = sup.Id, OriginCountryId = country.Id,
                Quantity = KpiRound(Demand(s, _currentMonth) * 2, multiple), OrderDate = etd.AddDays(-sup.ProductionLeadDays - 5),
                RequiredDate = _today.AddDays(Math.Max(2, daysLeft - 4)), Etd = etd, Eta = eta, Status = SupplyStatus.Shipped,
                Port = isLocal ? null : "Douala", Booking = $"BK{_rnd.Next(100000, 999999)}", BillOfLading = $"MEDU{_rnd.Next(1000000, 9999999)}", IsDemo = true,
            };
            line.Containers = Math.Ceiling(line.Quantity / perTc);
            db.SupplyLines.Add(line);
        }

        foreach (var po in pipeline)
        {
            var l = po.Line;
            if (po.Delivered)
            {
                l.Status = SupplyStatus.Delivered;
                l.ActualArrival = po.Arrival;
                l.DeliveredQty = _rnd.NextDouble() < 0.06 ? Math.Round(l.Quantity * 0.9) : l.Quantity;
                l.Etd = po.RevisedEtd;
            }
            else
            {
                l.Status = OpenStatus(po, isLocal);
                var plannedEtd = l.Etd!.Value;
                // Once goods have left, a shipping delay is known: both ETD and ETA are revised. A port delay is not (ETA simply passes).
                if (_today >= po.RevisedEtd && po.RevisedEtd > plannedEtd) { l.Etd = po.RevisedEtd; l.Eta = po.Arrival; }
                if (l.Status == SupplyStatus.Delayed) l.Eta = po.Arrival;
                if (l.Status is SupplyStatus.AtPort or SupplyStatus.Customs)
                    l.CustomsStatus = l.Status == SupplyStatus.Customs ? Pick("Déclaration déposée", "Inspection physique", "Paiement des droits en attente") : "Déchargement en attente";
                if (l.Status is SupplyStatus.Planned or SupplyStatus.Confirmed or SupplyStatus.InProduction) { l.Booking = null; l.BillOfLading = null; }
            }
            db.SupplyLines.Add(l);
        }

        // A couple of cancelled lines for realism.
        if (_rnd.NextDouble() < 0.08)
            db.SupplyLines.Add(new SupplyLine
            {
                PoNumber = (_poSeq++).ToString(), ProductId = p.Id, SupplierId = sup.Id, OriginCountryId = country.Id, Quantity = multiple,
                OrderDate = _today.AddDays(-60), Etd = _today.AddDays(-20), Eta = _today.AddDays(10), Status = SupplyStatus.Cancelled, IsDemo = true,
            });
    }

    private Po NewPo(Product p, Supplier sup, Country country, bool isLocal, DateOnly orderDate, double qty, double perTc)
    {
        var etd = orderDate.AddDays(sup.ProductionLeadDays + _rnd.Next(-3, 4));
        var eta = etd.AddDays(country.DefaultTransitDays + _rnd.Next(-3, 4));
        var r = _rnd.NextDouble();
        var delay = r < 0.72 ? 0 : r < 0.9 ? _rnd.Next(2, 11) : _rnd.Next(12, 31);
        var shippingDelay = delay > 0 && _rnd.NextDouble() < 0.5;
        var line = new SupplyLine
        {
            PoNumber = (_poSeq++).ToString(), ProductId = p.Id, SupplierId = sup.Id, OriginCountryId = country.Id, Quantity = qty,
            Containers = Math.Ceiling(qty / perTc), OrderDate = orderDate, RequiredDate = eta.AddDays(_rnd.Next(0, 8)), Etd = etd, Eta = eta,
            Port = isLocal ? null : "Douala", Booking = $"BK{_rnd.Next(100000, 999999)}", BillOfLading = isLocal ? null : $"MEDU{_rnd.Next(1000000, 9999999)}",
            IsDemo = true,
        };
        return new Po { Line = line, PlannedEta = eta, Arrival = eta.AddDays(delay), RevisedEtd = shippingDelay ? etd.AddDays(delay) : etd };
    }

    private SupplyStatus OpenStatus(Po po, bool isLocal)
    {
        var l = po.Line;
        var etd = l.Etd!.Value;
        if (_today < l.OrderDate.AddDays(3)) return SupplyStatus.Planned;
        if (_today < etd.AddDays(-5)) return _today < l.OrderDate.AddDays(8) ? SupplyStatus.Confirmed : SupplyStatus.InProduction;
        if (_today < po.RevisedEtd) return _today < etd ? SupplyStatus.Ready : SupplyStatus.Delayed;
        if (_today < po.PlannedEta) return SupplyStatus.Shipped;
        if (isLocal) return SupplyStatus.Delayed;
        return (_today.DayNumber - po.PlannedEta.DayNumber) < 5 ? SupplyStatus.AtPort : SupplyStatus.Customs;
    }

    private void AddForwardForecast(Spec s)
    {
        for (var i = 0; i <= 6; i++)
        {
            var m = _currentMonth.AddMonths(i);
            var f = Demand(s, m) * (1 + s.Bias * 0.5) * Noise(0.05);
            if (s.Profile == Profile.Dormant) f = 0;
            db.ForecastFacts.Add(new ForecastFact { DateKey = DateKeys.MonthKey(m), ProductId = s.Product.Id, ForecastQty = Math.Round(f), IsDemo = true });
        }
    }

    private void AddRiskRegister(List<Spec> specs, Dictionary<string, Supplier> suppliers)
    {
        var owners = new[] { "Responsable supply chain", "Responsable achats", "Responsable logistique", "Directeur commercial", "Directeur d'usine", "Contrôleur financier" };
        Spec Pick(Profile profile, MaterialType? type = null) =>
            specs.Where(s => s.Profile == profile && (type is null || s.Product.MaterialType == type)).OrderBy(_ => _rnd.Next()).FirstOrDefault() ?? specs[0];

        var n = 0;
        void Risk(RiskCategory cat, bool opp, string desc, Spec? spec, Supplier? sup, ImpactLevel impact, int prob, string action, int dueInDays, RiskStatus status)
        {
            db.RiskItems.Add(new RiskItem
            {
                Code = $"R-{++n:0000}", Category = cat, IsOpportunity = opp, Description = desc, ProductId = spec?.Product.Id, SupplierId = sup?.Id,
                Impact = impact, Probability = prob, Owner = owners[n % owners.Length], Action = action, DueDate = _today.AddDays(dueInDays),
                Status = status, CreatedAtUtc = clock.UtcNow.AddDays(-_rnd.Next(5, 60)), CreatedBy = "demo", IsDemo = true,
            });
        }

        var rahmaCritical = specs.First(s => s.Profile == Profile.Critical && s.Product.Description.StartsWith("FILM RAHMA"));
        Risk(RiskCategory.Stockout, false, $"Rupture imminente {rahmaCritical.Product.Description} — la production Rahma 500g s'arrêterait", rahmaCritical,
            suppliers["S01"], ImpactLevel.Critical, 80, "Demander expédition partielle par avion / relancer Anatolia Films", 3, RiskStatus.InProgress);
        Risk(RiskCategory.SupplyDelay, false, "Retards récurrents d'embarquement chez le fournisseur de films chinois", null, suppliers["S02"],
            ImpactLevel.High, 60, "Qualifier un second fournisseur de films", 30, RiskStatus.Open);
        Risk(RiskCategory.PortDelay, false, "Congestion au port de Douala: +7 jours de séjour conteneurs", null, null, ImpactLevel.High, 70,
            "Anticiper les commandes de 2 semaines; négocier la franchise de surestaries", 14, RiskStatus.Open);
        Risk(RiskCategory.Customs, false, "Nouvelle procédure de dédouanement des matières premières alimentaires", null, null, ImpactLevel.Medium, 50,
            "Former le transitaire; préparer les certificats phytosanitaires", -5, RiskStatus.InProgress);
        Risk(RiskCategory.Stockout, false, "Blé dur Ukraine: couverture inférieure à 1 mois", specs.First(s => s.Product.Description == "BLE DUR UKRAINE"), suppliers["S07"],
            ImpactLevel.Critical, 70, "Basculer une partie du besoin sur le blé canadien", 7, RiskStatus.Open);
        Risk(RiskCategory.Overstock, false, "Surstock de films Rahma pâtes courtes", specs.First(s => s.Product.Description.StartsWith("FILM RAHMA SHORT")), null,
            ImpactLevel.Medium, 90, "Décaler la prochaine commande; vérifier la cohérence du forecast", 21, RiskStatus.Open);
        Risk(RiskCategory.ForecastRisk, false, "Biais positif du forecast Armanti (+20 % sur 3 mois)", Pick(Profile.Healthy, MaterialType.FinishedGood), null,
            ImpactLevel.Medium, 60, "Revue du forecast Armanti avec les ventes au prochain S&OP", 10, RiskStatus.Open);
        Risk(RiskCategory.SupplierRisk, false, "Fournisseur de bocaux: capacité limitée en fin d'année", specs.First(s => s.Product.Description == "BOCAL VERRE 500ML"), suppliers["S16"],
            ImpactLevel.High, 40, "Sécuriser un contrat cadre T4", 45, RiskStatus.Open);
        Risk(RiskCategory.ProductionRisk, false, "Maintenance ligne spaghetti 2 prévue — capacité -30 % pendant 10 jours", Pick(Profile.Tight, MaterialType.FinishedGood), null,
            ImpactLevel.High, 100, "Constituer un stock tampon avant l'arrêt", 20, RiskStatus.InProgress);
        Risk(RiskCategory.DemandIncrease, true, "Projet Mayonnaise: référencement Fiona 500ml dans une nouvelle enseigne", specs.First(s => s.Product.Description == "MAYONNAISE FIONA 500ML"), null,
            ImpactLevel.High, 50, "Valider la capacité et les approvisionnements (bocaux, jaune d'oeuf)", 25, RiskStatus.Open);
        Risk(RiskCategory.DemandIncrease, true, "Hausse de la demande Garoua avant la saison des fêtes", Pick(Profile.Healthy, MaterialType.FinishedGood), null,
            ImpactLevel.Medium, 70, "Pré-positionner du stock à Garoua", 35, RiskStatus.Open);
        Risk(RiskCategory.ExcessStock, false, "Film neutre imprimé promo sans consommation depuis 4 mois", specs.First(s => s.Profile == Profile.Dormant), suppliers["S05"],
            ImpactLevel.Low, 100, "Décision S&OP: réutilisation ou mise au rebut", -2, RiskStatus.Open);
        Risk(RiskCategory.SupplyDelay, false, "Grève annoncée des transporteurs Douala–Yaoundé", null, null, ImpactLevel.Medium, 30,
            "Identifier des transporteurs alternatifs", 12, RiskStatus.Closed);
        Risk(RiskCategory.Overstock, true, "Opportunité: achat spot de semoule à prix réduit", specs.First(s => s.Product.Description == "SEMOULE SSSE PREMIUM"), suppliers["S08"],
            ImpactLevel.Medium, 40, "Évaluer l'impact trésorerie avec la Finance", 8, RiskStatus.Open);
    }

    private void AddActions(List<Spec> specs)
    {
        var risks = db.RiskItems.Local.ToDictionary(r => r.Code);
        var n = 0;
        void Action(string topic, string description, string owner, string dept, int dueInDays, ActionPriority priority, ActionStatus status,
            bool decision = false, string? risk = null, Spec? spec = null, string? comment = null, int ageDays = 10)
        {
            db.Actions.Add(new SopAction
            {
                Code = $"A-{++n:0000}", Date = _today.AddDays(-ageDays), Topic = topic, Description = description, Owner = owner, Department = dept,
                DueDate = _today.AddDays(dueInDays), Priority = priority, Status = status, IsDecision = decision, Comment = comment,
                RiskItemId = risk is not null && risks.TryGetValue(risk, out var r) ? r.Id : null, CArtSap = spec?.Product.CArtSap,
                CreatedAtUtc = clock.UtcNow.AddDays(-ageDays), CreatedBy = "demo", IsDemo = true,
            });
        }
        var rahma = specs.First(s => s.Profile == Profile.Critical && s.Product.Description.StartsWith("FILM RAHMA"));
        var wheat = specs.First(s => s.Product.Description == "BLE DUR UKRAINE");
        var mayo = specs.First(s => s.Product.Description == "MAYONNAISE FIONA 500ML");
        var dormant = specs.First(s => s.Profile == Profile.Dormant);

        Action("Films Rahma", "Obtenir d'Anatolia Films une expédition partielle par avion (2 t) pour couvrir la rupture du 08/10",
            "Planificateur appro (DÉMO)", "Supply Chain", 2, ActionPriority.Critical, ActionStatus.InProgress, risk: "R-0001", spec: rahma, comment: "Devis fret aérien demandé", ageDays: 4);
        Action("Films Rahma", "Valider le surcoût du fret aérien pour les films Rahma 500g", "Directeur général (DÉMO)", "Direction", 1,
            ActionPriority.Critical, ActionStatus.Open, decision: true, risk: "R-0001", spec: rahma, ageDays: 2);
        Action("Blé dur", "Basculer 30 % du besoin d'octobre sur le blé canadien", "Planificateur appro (DÉMO)", "Supply Chain", 5,
            ActionPriority.High, ActionStatus.Open, risk: "R-0005", spec: wheat, ageDays: 6);
        Action("Blé dur", "Arbitrer : achat spot de blé à prix majoré ou arrêt ligne 2 pendant 5 jours", "Directeur général (DÉMO)", "Direction", 3,
            ActionPriority.High, ActionStatus.Open, decision: true, risk: "R-0005", spec: wheat, ageDays: 2);
        Action("Port de Douala", "Négocier la franchise de surestaries avec le transitaire", "Chargé logistique (DÉMO)", "Logistique", -3,
            ActionPriority.High, ActionStatus.InProgress, risk: "R-0003", comment: "Relance envoyée", ageDays: 20);
        Action("Forecast", "Revue du forecast Armanti avec l'équipe commerciale", "Responsable commercial (DÉMO)", "Commercial", -6,
            ActionPriority.Medium, ActionStatus.Open, risk: "R-0007", ageDays: 25);
        Action("Projet Mayonnaise", "Confirmer la capacité bocaux 500 ml et jaune d'oeuf pour le nouveau référencement", "Responsable production (DÉMO)",
            "Production", 12, ActionPriority.High, ActionStatus.Open, risk: "R-0010", spec: mayo, ageDays: 5);
        Action("Projet Mayonnaise", "Go / No go du référencement Fiona 500 ml dans la nouvelle enseigne", "Directeur général (DÉMO)", "Direction", 9,
            ActionPriority.Medium, ActionStatus.Open, decision: true, risk: "R-0010", spec: mayo, ageDays: 3);
        Action("Stock dormant", "Décider réutilisation ou mise au rebut du film promo sans consommation", "Contrôleur financier (DÉMO)", "Finance", -1,
            ActionPriority.Medium, ActionStatus.Open, decision: true, risk: "R-0012", spec: dormant, ageDays: 15);
        Action("Maintenance", "Constituer 10 jours de stock tampon spaghetti avant l'arrêt de la ligne 2", "Responsable production (DÉMO)", "Production", 14,
            ActionPriority.High, ActionStatus.InProgress, risk: "R-0009", ageDays: 8);
        Action("Fournisseurs", "Qualifier un second fournisseur de films (appel d'offres)", "Planificateur appro (DÉMO)", "Supply Chain", 40,
            ActionPriority.Medium, ActionStatus.Open, risk: "R-0002", ageDays: 12);
        Action("Transport", "Identifier des transporteurs alternatifs Douala–Yaoundé", "Chargé logistique (DÉMO)", "Logistique", -10,
            ActionPriority.Low, ActionStatus.Done, risk: "R-0013", comment: "Deux transporteurs référencés", ageDays: 30);
    }

    /// <summary>
    /// Reporting catalogue shaped like the S&amp;OP reporting workbook (same IDs, departments and days), owned by the demo users,
    /// with 10 weeks of history and the current week in progress. Some reports are reliably on time, others often late.
    /// </summary>
    private void AddReporting()
    {
        const string sales = "Responsable commercial (DÉMO)", warehouse = "Responsable entrepôt (DÉMO)", supply = "Planificateur appro (DÉMO)",
            logistics = "Chargé logistique (DÉMO)", production = "Responsable production (DÉMO)", finance = "Contrôleur financier (DÉMO)";
        (string Code, string Dept, string Name, string Owner, string Freq, string Day, string Content, string? Time, string Purpose, double Reliability)[] catalogue =
        [
            ("COM-01", "Commercial", "Actual Sales", sales, "Weekly", "Saturday", "Sales actuals, CA, volumes, customers, products", "10:00", "Demand", 0.9),
            ("COM-02", "Commercial", "Sales Forecast S+1", sales, "Weekly", "Saturday", "Sales forecast for following week", "12:00", "Demand", 0.75),
            ("WH-01", "Warehouse", "Global Stock – FG Imported", warehouse, "Weekly", "Friday", "Global stock of imported finished goods", "16:00", "Stock", 0.95),
            ("WH-02", "Warehouse", "DLV / DLC Report", warehouse, "Weekly", "Wednesday", "DLV/DLC and expiry risks", "12:00", "Stock / Risk", 0.85),
            ("WH-03", "Warehouse", "Unstuffing / Dépotage", warehouse, "Weekly", "Friday", "Container unstuffing and depotage status", "16:00", "Transit / Warehouse", 0.8),
            ("WH-04", "Warehouse", "Global Warehouse Status", warehouse, "Weekly", "Friday", "Overall warehouse situation", "17:00", "Warehouse", 0.9),
            ("WH-05", "Warehouse", "Store Report – RM/PM, Films, Cartons", warehouse, "Weekly", "Every day", "Store situation for RM/PM, films, cartons", null, "Stock", 0.7),
            ("WH-06", "Warehouse", "Store Report – FG", warehouse, "Weekly", "Every day", "Local finished goods stock", null, "Stock", 0.8),
            ("SUP-01", "Supply / FG Imported", "Stock Port & En Mer", supply, "Weekly", "Friday", "TC at port, in transit and ETA", "12:00", "Supply", 0.95),
            ("SUP-02", "Supply / FG Imported", "Next 3 Months Visibility", supply, "Weekly / N3M", "Friday", "Three-month supply visibility", "15:00", "Supply", 0.85),
            ("SUP-03", "Supply / FG Imported", "Claims", supply, "Weekly", "Friday", "Claims on imported finished goods", "17:00", "Risk / Supply", 0.6),
            ("SUP-04", "Supply / RM-PM", "TC Visibility RM/PM", supply, "Weekly", "Friday", "TC and arrival visibility for RM/PM", "12:00", "Supply", 0.9),
            ("SUP-07", "Supply / RM-PM", "Plastic Films Status", supply, "Weekly", "Friday", "Films in production, at sea, at port", "15:00", "Supply", 0.85),
            ("TR-01", "Transit & Shipping", "CODIR Follow-up", logistics, "Weekly", "Saturday", "Transit, shipping, logistics and claims follow-up", "09:00", "Transit", 0.9),
            ("TR-02", "Transit & Shipping", "État TC", logistics, "Weekly", "Saturday", "TC navigation, quay, documents, DDI, delivery status", "09:00", "Transit", 0.85),
            ("PROD-01", "Production", "Actual Production", production, "Weekly", "Saturday", "Actual production from previous Saturday to Friday", "11:00", "Production", 0.55),
            ("PROD-02", "Production", "Production Plan / Forecast", production, "Weekly", "Saturday", "Production plan from Sunday to Saturday", "11:00", "Production", 0.75),
            ("LOG-01", "Logistics", "Delivery Tracking", logistics, "Weekly", "To confirm", "Delivery tracking", null, "Logistics", 0.7),
            ("FIN-01", "Finance", "Suppliers Paid / To Be Paid", finance, "Weekly", "Friday", "Supplier payments and possible blockers", "16:00", "Finance / Supply", 0.5),
            ("FIN-02", "Finance", "Customer Receivables", finance, "Weekly", "Friday", "Customer receivables", "16:00", "Finance / Demand", 0.6),
        ];

        var currentWeek = _today.AddDays(-(((int)_today.DayOfWeek + 6) % 7));
        foreach (var c in catalogue)
        {
            var def = new ReportDefinition
            {
                Code = c.Code, Department = c.Dept, Name = c.Name, Owner = c.Owner, Frequency = c.Freq, ExpectedDay = c.Day, ExpectedTime = c.Time,
                MainContent = c.Content, CatalogueStatus = c.Reliability >= 0.8 ? "Received" : "Identified", Purpose = c.Purpose, IsDemo = true,
            };
            db.ReportDefinitions.Add(def);
            for (var w = 10; w >= 0; w--)
            {
                var week = currentWeek.AddDays(-7 * w);
                var due = c.Day switch
                {
                    "Every day" => week,
                    "To confirm" => (DateOnly?)null,
                    var d => week.AddDays(((int)Enum.Parse<DayOfWeek>(d) + 6) % 7),
                };
                var s = new ReportSubmission
                {
                    Report = def, WeekStart = week, WeekLabel = $"S{System.Globalization.ISOWeek.GetWeekOfYear(week.ToDateTime(TimeOnly.MinValue)):00}",
                    ReferenceDate = week.AddDays(5), IsDemo = true,
                };
                var roll = _rnd.NextDouble();
                var reference = due ?? week.AddDays(4);
                if (reference >= _today)
                {
                    if (roll > 0.9) s.ReceivedDate = _today.AddDays(-1) < week ? week : _today.AddDays(-1);
                }
                else if (roll < c.Reliability)
                {
                    s.ReceivedDate = reference.AddDays(_rnd.NextDouble() < 0.3 ? -1 : 0);
                    s.Status = ReportStatus.Received;
                }
                else if (roll < c.Reliability + (1 - c.Reliability) * 0.6)
                {
                    var late = reference.AddDays(1 + _rnd.Next(3));
                    if (late < _today)
                    {
                        s.ReceivedDate = late;
                        s.Status = ReportStatus.Late;
                        s.Comments = Pick("Envoyé après relance", "Fichier incomplet, complété le lendemain", "Retard dû à la clôture mensuelle");
                    }
                    else s.RelanceRequired = true;
                }
                else if (w > 0)
                {
                    s.Status = ReportStatus.Missing;
                    s.RelanceRequired = true;
                    s.Comments = Pick("Pas de réponse", "Responsable absent", "Source ERP indisponible");
                }
                else s.RelanceRequired = true;
                if (s.ReceivedDate is not null)
                    s.Quality = _rnd.NextDouble() switch { < 0.85 => ReportQuality.Ok, < 0.95 => ReportQuality.Issue, _ => ReportQuality.Pending };
                if (s.Quality == ReportQuality.Issue) s.Comments ??= Pick("Colonnes manquantes", "Totaux incohérents avec la semaine précédente", "Format modifié");
                db.ReportSubmissions.Add(s);
            }
        }
    }

    private string Pick(params string[] values) => values[_rnd.Next(values.Length)];

    private static double KpiRound(double qty, double multiple) =>
        multiple > 0 ? Math.Max(multiple, Math.Ceiling(qty / multiple) * multiple) : Math.Ceiling(qty);
}
