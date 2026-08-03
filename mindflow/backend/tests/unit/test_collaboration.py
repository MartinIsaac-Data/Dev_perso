"""Mention parsing, handles, and share-link secrets.

Three small pieces with sharp edges. The mention regex has to reject email
addresses — a comment containing `contact@acme.com` must not mention `acme` —
and the share token has to be stored as a digest, because a database dump that
is also a set of live links is the kind of thing that ends up in a post-mortem.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domain.collaboration import (
    DEFAULT_SHARE_TTL,
    MAX_MENTIONS_PER_COMMENT,
    check_share,
    default_expiry,
    handle_for,
    hash_share_token,
    mint_share_token,
    parse_mentions,
)

NOW = datetime(2026, 8, 3, tzinfo=UTC)


class TestMentionParsing:
    def test_finds_a_simple_mention(self) -> None:
        found = parse_mentions("merci @sylvie pour le point")
        assert [m.handle for m in found] == ["sylvie"]

    def test_finds_several(self) -> None:
        found = parse_mentions("@paul et @marie.dupont, à vous")
        assert [m.handle for m in found] == ["paul", "marie.dupont"]

    def test_an_email_address_is_not_a_mention(self) -> None:
        # The failure that makes a comment notify a company domain. `@` preceded
        # by a word character is an address, not a mention.
        assert parse_mentions("écrire à contact@acme.com") == []

    def test_a_repeated_handle_notifies_once(self) -> None:
        # « @paul, and also @paul » is one notification, not two.
        found = parse_mentions("@paul et encore @paul")
        assert len(found) == 1

    def test_case_is_folded(self) -> None:
        assert parse_mentions("@Sylvie")[0].handle == "sylvie"

    def test_trailing_punctuation_is_dropped(self) -> None:
        assert parse_mentions("merci @sylvie.")[0].handle == "sylvie"

    def test_offsets_point_at_the_first_occurrence(self) -> None:
        found = parse_mentions("bonjour @paul")
        assert found[0].start == 8
        assert found[0].end == 13

    def test_a_broadcast_is_capped(self) -> None:
        # Fifty mentions is a broadcast, and broadcasts are how notification
        # systems get muted. Capped silently — the comment is still worth
        # saving.
        body = " ".join(f"@membre{index}" for index in range(60))
        assert len(parse_mentions(body)) == MAX_MENTIONS_PER_COMMENT

    def test_a_bare_at_sign_is_not_a_mention(self) -> None:
        assert parse_mentions("prix @ 12 euros") == []

    def test_an_empty_body_yields_nothing(self) -> None:
        assert parse_mentions("") == []


class TestHandles:
    def test_derived_from_the_email_local_part(self) -> None:
        # Display names collide constantly inside one company; email local
        # parts cannot.
        assert handle_for("marie.dupont@acme.com") == "marie.dupont"

    def test_case_and_spacing_are_folded(self) -> None:
        assert handle_for("  Marie.Dupont@ACME.com ") == "marie.dupont"

    def test_unusable_characters_are_stripped(self) -> None:
        assert handle_for("marie+notes@acme.com") == "marienotes"

    def test_falls_back_to_the_display_name(self) -> None:
        # Possible in federated identity setups; an empty handle is one nobody
        # can type.
        assert handle_for("+++@acme.com", display_name="Marie Dupont") == "mariedupont"

    def test_never_returns_empty(self) -> None:
        assert handle_for("@x") != ""

    def test_a_handle_round_trips_through_the_parser(self) -> None:
        # The property that makes mentions resolvable at all.
        handle = handle_for("marie.dupont@acme.com")
        assert parse_mentions(f"@{handle} bonjour")[0].handle == handle


class TestShareTokens:
    def test_the_plaintext_is_not_the_stored_value(self) -> None:
        token = mint_share_token()
        assert token.digest != token.plaintext
        assert len(token.digest) == 64

    def test_the_digest_is_reproducible(self) -> None:
        token = mint_share_token()
        assert hash_share_token(token.plaintext) == token.digest

    def test_two_tokens_differ(self) -> None:
        assert mint_share_token().plaintext != mint_share_token().plaintext

    def test_the_suffix_identifies_without_revealing(self) -> None:
        # Enough to tell two links apart in a list; not enough to reconstruct
        # one from a screenshot.
        token = mint_share_token()
        assert len(token.suffix) == 6
        assert token.suffix in token.plaintext
        assert len(token.plaintext) > 30


class TestShareValidity:
    def test_a_fresh_link_is_valid(self) -> None:
        assert check_share(revoked_at=None, expires_at=NOW + timedelta(days=1), now=NOW).valid

    def test_a_link_with_no_expiry_is_valid(self) -> None:
        assert check_share(revoked_at=None, expires_at=None, now=NOW).valid

    def test_an_expired_link_says_so(self) -> None:
        result = check_share(revoked_at=None, expires_at=NOW - timedelta(seconds=1), now=NOW)
        assert not result.valid
        assert "expiré" in result.reason

    def test_revocation_is_reported_before_expiry(self) -> None:
        # The two mean different things to the person following the link, and
        # to whoever audits it later.
        result = check_share(
            revoked_at=NOW - timedelta(days=2), expires_at=NOW - timedelta(days=1), now=NOW
        )
        assert not result.valid
        assert "révoqué" in result.reason

    def test_expiry_is_inclusive_of_the_instant(self) -> None:
        assert not check_share(revoked_at=None, expires_at=NOW, now=NOW).valid


class TestDefaultExpiry:
    def test_links_expire_by_default(self) -> None:
        # A link pasted into a chat two years ago must not still open.
        assert default_expiry(NOW) == NOW + DEFAULT_SHARE_TTL

    def test_the_default_is_a_month_not_a_decade(self) -> None:
        assert timedelta(days=7) <= DEFAULT_SHARE_TTL <= timedelta(days=90)
