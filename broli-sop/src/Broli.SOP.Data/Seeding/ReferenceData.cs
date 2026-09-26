namespace Broli.SOP.Data.Seeding;

/// <summary>
/// Reference data that is not demo data: countries (French name, English name accepted in imports) with typical transit
/// times to Douala.
/// </summary>
public static class ReferenceData
{
    public static readonly (string Code, string Name, string EnglishName, int TransitDays)[] Countries =
    [
        ("CM", "Cameroun", "Cameroon", 3), ("NG", "Nigeria", "Nigeria", 10), ("CI", "Côte d'Ivoire", "Ivory Coast", 8),
        ("GH", "Ghana", "Ghana", 9), ("TR", "Turquie", "Turkey", 30), ("CN", "Chine", "China", 45), ("IT", "Italie", "Italy", 28),
        ("FR", "France", "France", 25), ("ES", "Espagne", "Spain", 26), ("PT", "Portugal", "Portugal", 26),
        ("DE", "Allemagne", "Germany", 26), ("BE", "Belgique", "Belgium", 24), ("NL", "Pays-Bas", "Netherlands", 24),
        ("GR", "Grèce", "Greece", 28), ("PL", "Pologne", "Poland", 30), ("UA", "Ukraine", "Ukraine", 35), ("RU", "Russie", "Russia", 38),
        ("KZ", "Kazakhstan", "Kazakhstan", 42), ("IN", "Inde", "India", 35), ("MY", "Malaisie", "Malaysia", 40),
        ("TH", "Thaïlande", "Thailand", 40), ("VN", "Viêt Nam", "Vietnam", 42), ("AE", "Émirats arabes unis", "United Arab Emirates", 28),
        ("EG", "Égypte", "Egypt", 22), ("MA", "Maroc", "Morocco", 18), ("ZA", "Afrique du Sud", "South Africa", 20),
        ("CA", "Canada", "Canada", 32), ("US", "États-Unis", "United States", 30), ("BR", "Brésil", "Brazil", 32),
        ("AR", "Argentine", "Argentina", 35),
    ];
}
