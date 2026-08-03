"""Connector selection — the only module that maps a provider name to a class.

Same rule as `app/infra/ai/factory.py` (ADR-045), for the same reason: seven
integrations is exactly the number at which provider names start appearing in
service code, and once they do, removing one becomes a refactor instead of a
configuration change.

Imports are local to each branch so that a deployment using only Google
Calendar does not construct — or import — six other clients.
"""

from __future__ import annotations

from app.domain.sync import Provider, SyncConnectorPort
from app.infra.db.models.enterprise import IntegrationConnection


def build_connector(connection: IntegrationConnection, *, access_token: str) -> SyncConnectorPort:
    """The connector for a stored connection.

    Takes the decrypted token as an argument rather than decrypting here: this
    module has no business holding the key ring, and passing the plaintext in
    keeps the decryption in one auditable place (`integration_service`).
    """
    provider = Provider(connection.provider)
    settings = connection.settings or {}

    if provider is Provider.GOOGLE_CALENDAR:
        from app.infra.sync.connectors import GoogleCalendarConnector

        return GoogleCalendarConnector(
            token=access_token,
            calendar_id=str(settings.get("calendar_id", "primary")),
        )

    if provider in (Provider.OUTLOOK_CALENDAR, Provider.MICROSOFT_TODO):
        from app.infra.sync.connectors import MicrosoftGraphConnector

        # One class, one token, two products. The difference between them is a
        # resource path, not an integration.
        return MicrosoftGraphConnector(
            token=access_token,
            provider=provider,
            list_id=settings.get("list_id"),
        )

    if provider in (Provider.SLACK, Provider.TEAMS):
        from app.infra.sync.connectors import WebhookMessagingConnector

        return WebhookMessagingConnector(
            webhook_url=str(settings.get("webhook_url", "")),
            provider=provider,
        )

    if provider is Provider.NOTION:
        from app.infra.sync.connectors import NotionConnector

        return NotionConnector(
            token=access_token,
            database_id=str(settings.get("database_id", "")),
        )

    from app.infra.sync.connectors import ObsidianConnector

    # Obsidian needs no token: it is a folder, and the client writes the file.
    return ObsidianConnector(folder=str(settings.get("folder", "MindFlow")))
