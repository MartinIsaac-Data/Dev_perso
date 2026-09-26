using System.Net;
using System.Net.Mail;
using Broli.SOP.Application.Abstractions;
using Microsoft.Extensions.Configuration;

namespace Broli.SOP.Infrastructure;

/// <summary>
/// SMTP e-mail (e.g. the company relay or Microsoft 365). Configured with <c>Smtp:Host</c>, <c>Smtp:Port</c>, <c>Smtp:From</c>,
/// optional <c>Smtp:Username</c> / <c>Smtp:Password</c> (environment variables) and <c>Smtp:EnableSsl</c>.
/// Without a host, e-mail is simply not sent; in-app notifications still work.
/// </summary>
public sealed class SmtpEmailSender(IConfiguration config) : IEmailSender
{
    private string? Host => config["Smtp:Host"];
    public bool IsConfigured => !string.IsNullOrWhiteSpace(Host) && !string.IsNullOrWhiteSpace(config["Smtp:From"]);

    public async Task SendAsync(EmailMessage message, CancellationToken ct = default)
    {
        if (!IsConfigured) return;
        using var client = new SmtpClient(Host, config.GetValue("Smtp:Port", 25)) { EnableSsl = config.GetValue("Smtp:EnableSsl", true) };
        if (config["Smtp:Username"] is { Length: > 0 } user)
            client.Credentials = new NetworkCredential(user, config["Smtp:Password"]);
        using var mail = new MailMessage { From = new MailAddress(config["Smtp:From"]!), Subject = message.Subject, Body = message.Body };
        foreach (var to in message.To) mail.Bcc.Add(to);
        await client.SendMailAsync(mail, ct);
    }
}
