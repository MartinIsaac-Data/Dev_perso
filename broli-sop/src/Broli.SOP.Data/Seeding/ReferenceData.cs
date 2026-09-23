namespace Broli.SOP.Data.Seeding;

/// <summary>Reference data that is not demo data: countries with typical transit times to Douala.</summary>
public static class ReferenceData
{
    public static readonly (string Code, string Name, int TransitDays)[] Countries =
    [
        ("CM", "Cameroon", 3), ("NG", "Nigeria", 10), ("CI", "Côte d'Ivoire", 8), ("GH", "Ghana", 9), ("TR", "Turkey", 30),
        ("CN", "China", 45), ("IT", "Italy", 28), ("FR", "France", 25), ("ES", "Spain", 26), ("PT", "Portugal", 26),
        ("DE", "Germany", 26), ("BE", "Belgium", 24), ("NL", "Netherlands", 24), ("GR", "Greece", 28), ("PL", "Poland", 30),
        ("UA", "Ukraine", 35), ("RU", "Russia", 38), ("KZ", "Kazakhstan", 42), ("IN", "India", 35), ("MY", "Malaysia", 40),
        ("TH", "Thailand", 40), ("VN", "Vietnam", 42), ("AE", "United Arab Emirates", 28), ("EG", "Egypt", 22), ("MA", "Morocco", 18),
        ("ZA", "South Africa", 20), ("CA", "Canada", 32), ("US", "United States", 30), ("BR", "Brazil", 32), ("AR", "Argentina", 35),
    ];
}
