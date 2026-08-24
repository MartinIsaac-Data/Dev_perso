"""OAuth 2.0, la partie qui se décide sans réseau.

Ce module ne parle à personne. Il décrit ce que chaque fournisseur attend, ce
qu'un octroi contient, et **quand un jeton doit être renouvelé** — trois choses
qui étaient jusqu'ici absentes, avec une conséquence simple : un jeton Google
vit une heure, et rien ne le renouvelait. Une connexion tenait soixante minutes,
puis passait en `expired`, définitivement (ADR-056).

Trois pièges sont encodés ici plutôt que documentés ailleurs, parce qu'ils
coûtent chacun une demi-journée à qui les rencontre sans les connaître.

**Google ne rend un jeton de rafraîchissement que si on le demande.** Sans
`access_type=offline` *et* `prompt=consent`, l'échange renvoie un jeton d'accès
d'une heure et rien pour le renouveler — c'est-à-dire exactement le bogue qu'on
répare, reproduit à l'identique. Pire : la deuxième autorisation d'un même
compte n'en renvoie pas non plus, donc le défaut n'apparaît qu'au second essai.

**Microsoft fait tourner ses jetons de rafraîchissement, pas Google.** Une
réponse de renouvellement Microsoft contient un *nouveau* `refresh_token` qu'il
faut stocker ; une réponse Google n'en contient aucun et il faut garder
l'ancien. Écraser avec `None` casse la connexion au renouvellement suivant.

**`invalid_grant` est terminal, le reste ne l'est pas.** Un octroi révoqué ne
guérit jamais ; une panne réseau, si. Confondre les deux donne soit des
reconnexions demandées pour rien, soit un compteur d'échecs qui monte
indéfiniment contre un jeton mort.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.domain.sync import Provider

# De combien on anticipe l'expiration.
#
# Renouveler *avant* plutôt qu'attendre un 401 : une passe de synchronisation
# qui échoue puis renouvelle a perdu son tour, et avec une cadence de cinq
# minutes cela se voit. Deux minutes couvrent le temps d'une passe complète et
# la dérive d'horloge entre nous et le fournisseur.
REFRESH_MARGIN = timedelta(minutes=2)

# Durée de validité d'une demande d'autorisation. Le temps de voir un écran de
# consentement, pas celui d'aller déjeuner : au-delà, un `state` qui traîne dans
# un historique de navigateur devient une pièce rejouable.
STATE_TTL = timedelta(minutes=15)


class OAuthError(RuntimeError):
    """Échec d'un échange de jetons.

    `terminal` distingue « cet octroi est mort, il faut redemander à
    l'utilisateur » de « réessayez tout à l'heure ». C'est la seule chose que
    l'appelant a besoin de savoir.
    """

    def __init__(self, message: str, *, terminal: bool = False) -> None:
        super().__init__(message)
        self.terminal = terminal


@dataclass(frozen=True, slots=True)
class OAuthProvider:
    """Ce qu'un fournisseur attend, en données plutôt qu'en `if`."""

    provider: Provider
    authorize_url: str
    exchange_url: str
    scopes: tuple[str, ...]
    # Paramètres ajoutés à la seule demande d'autorisation. C'est ici que vit
    # `access_type=offline`, dont l'absence est invisible jusqu'à la 61e minute.
    extra_authorize_params: dict[str, str] = field(default_factory=dict)

    @property
    def scope_value(self) -> str:
        return " ".join(self.scopes)


# Microsoft Graph sert Outlook et To Do avec un seul jeton : une seule
# application enregistrée, deux entrées ici, parce que l'utilisateur les
# connecte séparément et peut n'en vouloir qu'une.
_MICROSOFT_AUTHORIZE = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
_MICROSOFT_EXCHANGE = "https://login.microsoftonline.com/common/oauth2/v2.0/token"

# `offline_access` est ce qui, chez Microsoft, joue le rôle d'`access_type` chez
# Google : sans lui, pas de jeton de rafraîchissement.
_MICROSOFT_BASE_SCOPES = ("offline_access",)

PROVIDERS: dict[Provider, OAuthProvider] = {
    Provider.GOOGLE_CALENDAR: OAuthProvider(
        provider=Provider.GOOGLE_CALENDAR,
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        exchange_url="https://oauth2.googleapis.com/token",
        # `calendar.events` et non `calendar` : lire et écrire des événements,
        # pas créer ou supprimer des agendas entiers. Le moindre privilège se
        # décide ici, une fois, pas à la revue de sécurité.
        scopes=("https://www.googleapis.com/auth/calendar.events",),
        extra_authorize_params={
            "access_type": "offline",
            # Forcé : sans lui, une deuxième autorisation du même compte ne
            # renvoie pas de jeton de rafraîchissement, et la connexion meurt à
            # la 61e minute pour une raison introuvable.
            "prompt": "consent",
            "include_granted_scopes": "true",
        },
    ),
    Provider.OUTLOOK_CALENDAR: OAuthProvider(
        provider=Provider.OUTLOOK_CALENDAR,
        authorize_url=_MICROSOFT_AUTHORIZE,
        exchange_url=_MICROSOFT_EXCHANGE,
        scopes=(*_MICROSOFT_BASE_SCOPES, "https://graph.microsoft.com/Calendars.ReadWrite"),
    ),
    Provider.MICROSOFT_TODO: OAuthProvider(
        provider=Provider.MICROSOFT_TODO,
        authorize_url=_MICROSOFT_AUTHORIZE,
        exchange_url=_MICROSOFT_EXCHANGE,
        scopes=(*_MICROSOFT_BASE_SCOPES, "https://graph.microsoft.com/Tasks.ReadWrite"),
    ),
}


def supports_oauth(provider: Provider) -> bool:
    """Les fournisseurs qui passent par un échange de jetons.

    Slack et Teams n'y sont pas : leur secret est une URL de webhook entrant,
    qui n'expire pas. Notion non plus : un jeton d'intégration interne n'expire
    pas davantage. Les faire passer par ce flux ajouterait une cérémonie sans
    rien résoudre — et masquerait qu'ils fonctionnent déjà.
    """
    return provider in PROVIDERS


def provider_config(provider: Provider) -> OAuthProvider:
    config = PROVIDERS.get(provider)
    if config is None:
        raise OAuthError(f"{provider.label} ne passe pas par OAuth.", terminal=True)
    return config


@dataclass(frozen=True, slots=True)
class TokenGrant:
    """Ce qu'un fournisseur rend, une fois normalisé."""

    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    scope: str = ""

    def merged_with(self, previous_refresh_token: str | None) -> TokenGrant:
        """Conserve l'ancien jeton de rafraîchissement quand il n'en revient pas.

        Google n'en renvoie pas au renouvellement ; Microsoft en renvoie un
        nouveau. Écraser avec `None` dans le premier cas casse la connexion au
        renouvellement suivant — une heure plus tard, loin de la cause.
        """
        if self.refresh_token:
            return self
        return TokenGrant(
            access_token=self.access_token,
            refresh_token=previous_refresh_token,
            expires_at=self.expires_at,
            scope=self.scope,
        )


def expiry_from(expires_in: object, *, now: datetime | None = None) -> datetime | None:
    """`expires_in` (secondes) → instant d'expiration.

    Rend `None` plutôt que de deviner quand la valeur est absente ou illisible :
    un jeton sans expiration connue est renouvelé sur 401, ce qui est le bon
    repli. Inventer une durée produirait des renouvellements inutiles, ou pire,
    tardifs.
    """
    if isinstance(expires_in, bool) or not isinstance(expires_in, (int, float, str)):
        return None
    try:
        seconds = int(float(expires_in))
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return (now or datetime.now(UTC)) + timedelta(seconds=seconds)


def needs_refresh(
    expires_at: datetime | None,
    *,
    now: datetime | None = None,
    margin: timedelta = REFRESH_MARGIN,
) -> bool:
    """Faut-il renouveler maintenant ?

    Sans expiration connue, non : on ne renouvelle pas un jeton dont rien ne dit
    qu'il est fatigué. Le 401 reste le filet.
    """
    if expires_at is None:
        return False
    moment = now or datetime.now(UTC)
    if expires_at.tzinfo is None:
        # Les colonnes `TIMESTAMP WITHOUT TIME ZONE` remontent naïves ; les
        # traiter comme locales décalerait l'expiration de plusieurs heures.
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at - margin <= moment


def make_pkce_pair() -> tuple[str, str]:
    """`(verifier, challenge)` en S256.

    PKCE alors que nous sommes un client confidentiel — nous avons un secret
    côté serveur — parce que cela ne coûte rien et protège du cas où le code
    d'autorisation fuite du navigateur : sans le vérificateur, il ne s'échange
    pas. RFC 7636 §4.2 : base64url sans remplissage.
    """
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge
