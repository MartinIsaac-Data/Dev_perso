using System.Globalization;
using System.Text;
using Broli.SOP.Application.Abstractions;
using ClosedXML.Excel;

namespace Broli.SOP.Infrastructure;

public sealed class ExcelReader : IExcelReader
{
    public const int MaxRows = 500_000;

    /// <summary>Reads the sheet named like the template (else the first one). The header is the first non-empty row.</summary>
    public RawSheet Read(Stream stream, string? preferredSheet)
    {
        using var wb = new XLWorkbook(stream);
        var ws = wb.Worksheets.FirstOrDefault(w => preferredSheet is not null && string.Equals(w.Name.Trim(), preferredSheet, StringComparison.OrdinalIgnoreCase))
                 ?? wb.Worksheets.First();
        return ReadSheet(ws);
    }

    public IReadOnlyList<NamedSheet> ReadAll(Stream stream)
    {
        using var wb = new XLWorkbook(stream);
        return wb.Worksheets.Select(ws => new NamedSheet(ws.Name.Trim(), ReadSheet(ws))).ToList();
    }

    private static RawSheet ReadSheet(IXLWorksheet ws)
    {
        var used = ws.RangeUsed();
        if (used is null) return new RawSheet([], []);

        var firstRow = used.FirstRow().RowNumber();
        var lastRow = used.LastRow().RowNumber();
        var firstCol = used.FirstColumn().ColumnNumber();
        var lastCol = used.LastColumn().ColumnNumber();
        if (lastRow - firstRow > MaxRows) throw new InvalidDataException($"La feuille « {ws.Name} » dépasse {MaxRows:N0} lignes.");

        var headers = new List<string>();
        for (var c = firstCol; c <= lastCol; c++) headers.Add(ws.Cell(firstRow, c).GetString().Trim());
        while (headers.Count > 0 && headers[^1].Length == 0) headers.RemoveAt(headers.Count - 1);

        var rows = new List<RawRow>();
        for (var r = firstRow + 1; r <= lastRow; r++)
        {
            var cells = new object?[headers.Count];
            var empty = true;
            for (var c = 0; c < headers.Count; c++)
            {
                var cell = ws.Cell(r, firstCol + c);
                object? value = cell.Value.Type switch
                {
                    XLDataType.Blank => null,
                    XLDataType.Number => cell.Value.GetNumber(),
                    XLDataType.DateTime => cell.Value.GetDateTime(),
                    XLDataType.Boolean => cell.Value.GetBoolean(),
                    XLDataType.Text => cell.Value.GetText(),
                    XLDataType.TimeSpan => cell.Value.GetTimeSpan().ToString(),
                    XLDataType.Error => $"#ERROR",
                    _ => cell.GetString(),
                };
                if (value is string s && string.IsNullOrWhiteSpace(s)) value = null;
                if (value is not null) empty = false;
                cells[c] = value;
            }
            if (!empty) rows.Add(new RawRow(r, cells));
        }
        return new RawSheet(headers, rows);
    }
}

public sealed class TabularExporter : ITabularExporter
{
    private static readonly XLColor Header = XLColor.FromHtml("#0F2A47");

    public byte[] ToXlsx(TableData table)
    {
        using var wb = new XLWorkbook();
        var ws = wb.Worksheets.Add(SheetName(table.Title));
        ws.Cell(1, 1).Value = table.Title;
        ws.Cell(1, 1).Style.Font.SetBold().Font.SetFontSize(14);
        ws.Cell(2, 1).Value = table.Subtitle ?? "";
        ws.Cell(2, 1).Style.Font.SetItalic().Font.SetFontColor(XLColor.Gray);
        ws.Cell(3, 1).Value = $"Exporté le {DateTime.Now:dd/MM/yyyy HH:mm} — Portail S&OP Broli";
        ws.Cell(3, 1).Style.Font.SetFontColor(XLColor.Gray);

        const int headerRow = 5;
        for (var c = 0; c < table.Columns.Count; c++)
        {
            var cell = ws.Cell(headerRow, c + 1);
            cell.Value = table.Columns[c].Header;
            cell.Style.Font.SetBold().Font.SetFontColor(XLColor.White).Fill.SetBackgroundColor(Header);
        }
        for (var r = 0; r < table.Rows.Count; r++)
        {
            var row = table.Rows[r];
            for (var c = 0; c < table.Columns.Count && c < row.Length; c++)
            {
                var cell = ws.Cell(headerRow + 1 + r, c + 1);
                switch (row[c])
                {
                    case null: break;
                    case double d when double.IsFinite(d): cell.Value = d; break;
                    case int i: cell.Value = i; break;
                    case long l: cell.Value = l; break;
                    case DateOnly dt: cell.Value = dt.ToDateTime(TimeOnly.MinValue); break;
                    case DateTime dt: cell.Value = dt; break;
                    case bool b: cell.Value = b ? "Oui" : "Non"; break;
                    default: cell.Value = row[c]!.ToString(); break;
                }
                cell.Style.NumberFormat.Format = table.Columns[c].Format switch
                {
                    "number" => "#,##0",
                    "decimal" => "#,##0.0",
                    "date" => "dd/mm/yyyy",
                    _ => cell.Style.NumberFormat.Format,
                };
            }
        }
        if (table.Rows.Count > 0)
            ws.Range(headerRow, 1, headerRow + table.Rows.Count, table.Columns.Count).SetAutoFilter();
        ws.SheetView.FreezeRows(headerRow);
        ws.Columns(1, table.Columns.Count).AdjustToContents(headerRow, Math.Min(headerRow + 200, headerRow + table.Rows.Count), 8, 60);
        return Save(wb);
    }

    /// <summary>CSV with ';' separator and a UTF-8 BOM so that French-locale Excel opens it correctly.</summary>
    public byte[] ToCsv(TableData table)
    {
        var sb = new StringBuilder();
        sb.AppendLine(string.Join(';', table.Columns.Select(c => Escape(c.Header))));
        foreach (var row in table.Rows)
            sb.AppendLine(string.Join(';', row.Select(v => Escape(v switch
            {
                null => "",
                double d when double.IsFinite(d) => d.ToString("0.##", CultureInfo.GetCultureInfo("fr-FR")),
                double => "",
                DateOnly dt => dt.ToString("dd/MM/yyyy", CultureInfo.InvariantCulture),
                DateTime dt => dt.ToString("dd/MM/yyyy HH:mm", CultureInfo.InvariantCulture),
                bool b => b ? "Oui" : "Non",
                _ => Convert.ToString(v, CultureInfo.InvariantCulture) ?? "",
            }))));
        return [.. Encoding.UTF8.GetPreamble(), .. Encoding.UTF8.GetBytes(sb.ToString())];
    }

    public byte[] Template(string sheetName, IReadOnlyList<string> required, IReadOnlyList<string> optional, IReadOnlyList<object?[]> example, string notes)
    {
        using var wb = new XLWorkbook();
        var ws = wb.Worksheets.Add(SheetName(sheetName));
        var columns = required.Concat(optional).ToList();
        for (var c = 0; c < columns.Count; c++)
        {
            var cell = ws.Cell(1, c + 1);
            cell.Value = columns[c];
            var isRequired = c < required.Count;
            cell.Style.Font.SetBold().Font.SetFontColor(XLColor.White)
                .Fill.SetBackgroundColor(isRequired ? Header : XLColor.FromHtml("#5B7A99"));
            cell.CreateComment().AddText(isRequired ? "Required" : "Optional");
        }
        for (var r = 0; r < example.Count; r++)
            for (var c = 0; c < example[r].Length && c < columns.Count; c++)
            {
                var cell = ws.Cell(r + 2, c + 1);
                switch (example[r][c])
                {
                    case null: break;
                    case DateTime dt: cell.Value = dt; cell.Style.NumberFormat.Format = "dd/mm/yyyy"; break;
                    case double d: cell.Value = d; break;
                    case int i: cell.Value = i; break;
                    default: cell.Value = example[r][c]!.ToString(); break;
                }
            }
        ws.SheetView.FreezeRows(1);
        ws.Columns().AdjustToContents();

        var help = wb.Worksheets.Add("README");
        var lines = notes.Split('\n');
        for (var i = 0; i < lines.Length; i++) help.Cell(i + 1, 1).Value = lines[i];
        help.Cell(lines.Length + 2, 1).Value = "Dark blue headers are required; light blue headers are optional.";
        help.Column(1).Width = 110;
        return Save(wb);
    }

    private static string Escape(string s) =>
        s.IndexOfAny([';', '"', '\n', '\r']) >= 0 ? "\"" + s.Replace("\"", "\"\"") + "\"" : s;

    private static string SheetName(string title)
    {
        var clean = new string(title.Where(c => !"[]:*?/\\".Contains(c)).ToArray());
        return clean.Length > 31 ? clean[..31] : clean;
    }

    private static byte[] Save(XLWorkbook wb)
    {
        using var ms = new MemoryStream();
        wb.SaveAs(ms);
        return ms.ToArray();
    }
}
