"""What is the user actually asking for?

The five questions the product must answer are not one kind of question:

| Question | What answers it |
| --- | --- |
| « Que dois-je faire aujourd'hui ? » | A **query** against the agenda. No retrieval, no model |
| « Quelles sont mes tâches en retard ? » | A **query**. Same |
| « Résume mes réunions » | **Retrieval** over meetings, then a model |
| « Montre les notes concernant le Forecast Gabon » | **Retrieval**, then a list — no prose needed |
| « Quels sujets reviennent souvent ? » | **Aggregation** over entities, then a model |

Routing them all through a language model would be slower, more expensive and —
for the first two — *less accurate*, because "what is due today" is a fact the
database knows exactly and a model can only approximate.

So intent is classified **deterministically first**. The classifier here is a
small ordered set of patterns; it either matches with confidence or it does not.
When it does not, the assistant falls back to retrieval-augmented generation,
which is the general case and always a defensible answer.

This ordering — rules, then the model — is the same principle as ADR-020 for
dates: what can be computed exactly should never be guessed.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum


class Intent(StrEnum):
    """What kind of answer the question wants."""

    # Answered from structured data alone. Fast, exact, free.
    TODAY = "today"
    OVERDUE = "overdue"
    UPCOMING = "upcoming"
    # Answered by retrieval, then generation.
    SUMMARISE = "summarise"
    RECALL = "recall"
    # Answered by aggregation over extracted entities.
    THEMES = "themes"
    PEOPLE = "people"
    # Everything else.
    OPEN_QUESTION = "open_question"

    @property
    def needs_generation(self) -> bool:
        """Whether a model has to write prose.

        `TODAY` and `OVERDUE` do not: the answer is a list, and rendering a list
        as a paragraph adds latency, cost and an opportunity to be wrong.
        """
        return self not in (Intent.TODAY, Intent.OVERDUE, Intent.UPCOMING)

    @property
    def needs_retrieval(self) -> bool:
        return self in (Intent.SUMMARISE, Intent.RECALL, Intent.OPEN_QUESTION)


@dataclass(frozen=True, slots=True)
class Classification:
    intent: Intent
    confidence: float
    # What the pattern captured — a subject, a type filter, a window. Passed to
    # the handler so "résume mes réunions de la semaine" narrows correctly.
    subject: str | None = None
    entry_type: str | None = None
    window_days: int | None = None
    matched: str | None = None

    @property
    def is_confident(self) -> bool:
        return self.confidence >= 0.7


@dataclass(slots=True)
class _Rule:
    intent: Intent
    pattern: re.Pattern[str]
    confidence: float = 0.9
    entry_type: str | None = None
    window_days: int | None = None
    subject_group: str | None = None


# U+2019 is spelled as an escape rather than pasted: iOS substitutes the curly
# apostrophe silently, so the class must cover it, but a literal curly quote
# inside a character class is indistinguishable from a typo in review.
_SEPARATORS = re.compile("[\u2019'\\-_]+")


def _normalise(text: str) -> str:
    """Lower-case, strip accents, and flatten apostrophes and hyphens to spaces.

    People dictate to this product; a phone keyboard eats accents constantly and
    a classifier that cares about them fails on half the real input. Apostrophes
    go the same way for the same reason — transcription produces « aujourd hui »
    and « que dois je faire » as often as the typographically correct forms, and
    those must not route differently from each other.
    """
    stripped = "".join(
        char
        for char in unicodedata.normalize("NFD", text.lower().strip())
        if unicodedata.category(char) != "Mn"
    )
    return re.sub(r"\s+", " ", _SEPARATORS.sub(" ", stripped)).strip()


# Order matters: the first match wins, so the specific precedes the general.
# "resume mes reunions" must not be caught by the bare "resume".
#
# Patterns are written against the *normalised* form, where apostrophes and
# hyphens have already become spaces — hence `aujourd hui`, not `aujourd'hui`.
_RULES: tuple[_Rule, ...] = (
    _Rule(
        Intent.OVERDUE,
        re.compile(r"\b(en retard|retard|depassee?s?|overdue|pas faites?|oubliees?)\b"),
    ),
    _Rule(
        Intent.TODAY,
        re.compile(
            r"\b(aujourd ?hui|ce jour|today|"
            r"que dois ?je faire|quoi faire|mon programme|ma journee)\b"
        ),
    ),
    _Rule(
        Intent.UPCOMING,
        re.compile(r"\b(cette semaine|prochains? jours?|a venir|semaine prochaine|demain)\b"),
        window_days=7,
    ),
    _Rule(
        Intent.SUMMARISE,
        re.compile(r"\b(resume|resumer|synthese|synthetise|recapitul\w*)\b.{0,30}\breunions?\b"),
        entry_type="meeting",
        confidence=0.95,
    ),
    _Rule(
        Intent.SUMMARISE,
        re.compile(r"\b(resume|resumer|synthese|synthetise|recapitul\w*|bilan)\b"),
        confidence=0.8,
    ),
    _Rule(
        Intent.THEMES,
        re.compile(
            r"\b(sujets?|themes?|thematiques?|recurrent\w*|reviennent|revient|souvent|"
            r"de quoi je parle)\b"
        ),
    ),
    _Rule(
        Intent.PEOPLE,
        re.compile(r"\b(qui|personnes?|interlocuteurs?|avec qui)\b.{0,30}\b(parle|vu|rencontre)\b"),
    ),
    _Rule(
        Intent.RECALL,
        re.compile(
            r"\b(montre|montrer|affiche|trouve|retrouve|cherche|liste|"
            r"notes? (concernant|sur|a propos))\b(?P<subject>.*)"
        ),
        subject_group="subject",
        confidence=0.85,
    ),
)

# Words that carry no meaning once the verb has been consumed. Stripped from the
# captured subject so "montre les notes concernant le Forecast Gabon" searches
# for "Forecast Gabon", not for "les notes concernant le Forecast Gabon".
_SUBJECT_NOISE = re.compile(
    r"^\s*(les?|la|des?|du|mes|mon|ma|toutes?|tous|"
    r"notes?|entrees?|elements?|concernant|sur|a propos de|au sujet de|pour|dans)\s+",
    re.IGNORECASE,
)


def classify(question: str) -> Classification:
    """Classify a question. Never raises; the fallback is always answerable."""
    if not question or not question.strip():
        return Classification(Intent.OPEN_QUESTION, confidence=0.0)

    text = _normalise(question)

    for rule in _RULES:
        match = rule.pattern.search(text)
        if match is None:
            continue

        subject: str | None = None
        if rule.subject_group:
            raw = match.groupdict().get(rule.subject_group) or ""
            subject = _clean_subject(raw)
            # A verb with nothing after it is not a recall — "montre" alone is a
            # request for something the classifier cannot name.
            if not subject:
                continue

        return Classification(
            intent=rule.intent,
            confidence=rule.confidence,
            subject=subject,
            entry_type=rule.entry_type,
            window_days=rule.window_days,
            matched=match.group(0).strip(),
        )

    # No rule fired. That is the *normal* case for an open question, and RAG is
    # the right handler for it — the low confidence says "no shortcut applied",
    # not "I do not understand".
    return Classification(Intent.OPEN_QUESTION, confidence=0.4, subject=question.strip())


def _clean_subject(raw: str) -> str:
    """Strip leading articles and connectives from a captured subject."""
    subject = raw.strip(" ?.!,;:")
    previous = None
    while subject and subject != previous:
        previous = subject
        subject = _SUBJECT_NOISE.sub("", subject).strip()
    return subject


@dataclass(slots=True)
class AssistantPlan:
    """How the assistant will answer, decided before anything is called.

    Made explicit so it can be logged and shown: an assistant that says "j'ai
    cherché dans vos réunions de la semaine" is far easier to trust — and to
    correct — than one that simply produces an answer.
    """

    classification: Classification
    use_retrieval: bool
    use_generation: bool
    search_query: str
    entry_types: tuple[str, ...] = ()
    window_days: int | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def intent(self) -> Intent:
        return self.classification.intent


def plan(question: str) -> AssistantPlan:
    """Turn a question into a plan."""
    classification = classify(question)
    intent = classification.intent

    search_query = classification.subject or question.strip()
    entry_types: tuple[str, ...] = ()
    if classification.entry_type:
        entry_types = (classification.entry_type,)

    notes: list[str] = []
    if intent in (Intent.TODAY, Intent.OVERDUE, Intent.UPCOMING):
        notes.append("Réponse construite depuis vos échéances, sans modèle de langage.")
    elif intent is Intent.THEMES:
        notes.append("Réponse construite depuis les entités extraites de vos captures.")

    return AssistantPlan(
        classification=classification,
        use_retrieval=intent.needs_retrieval,
        use_generation=intent.needs_generation,
        search_query=search_query,
        entry_types=entry_types,
        window_days=classification.window_days,
        notes=notes,
    )
