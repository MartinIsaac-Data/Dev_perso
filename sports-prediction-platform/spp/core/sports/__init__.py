"""Registre des adaptateurs de sport.

Importer ce paquet enregistre les trois sports de la V1/V2. Ajouter un sport
consiste à écrire un module et à l'importer ici.
"""

from spp.core.sports.base import SportAdapter, get_adapter, register, registered_sports
from spp.core.sports.basketball import BASKETBALL
from spp.core.sports.football import FOOTBALL
from spp.core.sports.tennis import TENNIS

__all__ = [
    "BASKETBALL",
    "FOOTBALL",
    "TENNIS",
    "SportAdapter",
    "get_adapter",
    "register",
    "registered_sports",
]
