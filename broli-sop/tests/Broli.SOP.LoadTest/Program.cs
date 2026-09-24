using Broli.SOP.LoadTest;

// Usage:
//   seed <db-path> [skus=3000] [months=48]
//   run <api-url> <user> <password> [users=50] [seconds=120] [thinkMs=2000] [report=load-report.md]
if (args.Length >= 2 && args[0] == "seed")
{
    Seed.Run(args[1], args.Length > 2 ? int.Parse(args[2]) : 3000, args.Length > 3 ? int.Parse(args[3]) : 48, 2026);
    return 0;
}
if (args.Length >= 4 && args[0] == "run")
{
    return await Load.RunAsync(args[1], args[2], args[3],
        args.Length > 4 ? int.Parse(args[4]) : 50, args.Length > 5 ? int.Parse(args[5]) : 120,
        args.Length > 6 ? int.Parse(args[6]) : 2000, args.Length > 7 ? args[7] : "load-report.md");
}
Console.Error.WriteLine("Usage: seed <db> [skus] [months] | run <api> <user> <password> [users] [seconds] [thinkMs] [report]");
return 2;
