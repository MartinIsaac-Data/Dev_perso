"""The static snapshot that becomes the public demonstration site.

Two things are being protected here, and the second is easy to lose sight of.

**Nothing real gets published.** The generator refuses a profile not flagged
as demo, and strips every other profile out of the responses that list them.
A test asserts both, because the whole file is destined for a public URL and
the mistake would be silent.

**The front end and the generator agree on the canonical URL.** The snapshot
is keyed by the full request path including sorted query parameters. If the
two ever disagree, every affected view breaks — so the ordering rule is
asserted rather than assumed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.services.snapshot import canonical, generate, planned_requests

REPO_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


class TestCanonicalUrl:
    def test_parameters_are_sorted(self) -> None:
        # ?limit=8&profile=demo and ?profile=demo&limit=8 are the same request
        # and must not become two snapshot keys.
        assert canonical("/x", {"profile": "demo", "limit": 8}) == "/x?limit=8&profile=demo"
        assert canonical("/x", {"limit": 8, "profile": "demo"}) == "/x?limit=8&profile=demo"

    def test_empty_and_none_values_are_dropped(self) -> None:
        assert canonical("/x", {"a": None, "b": "", "c": 1}) == "/x?c=1"

    def test_no_params_means_no_question_mark(self) -> None:
        assert canonical("/x") == "/x"
        assert canonical("/x", {}) == "/x"
        assert canonical("/x", {"a": None}) == "/x"

    def test_matches_the_typescript_client_ordering_rule(self) -> None:
        """The TS client sorts by key with the same comparison.

        Read from the source rather than trusted: if someone removes the sort
        from `query()`, this fails and names the file.
        """
        client = (REPO_FRONTEND / "src" / "api" / "client.ts").read_text(encoding="utf-8")
        assert ".sort(([a], [b])" in client, "query() in client.ts no longer sorts parameters"


class TestPlannedRequests:
    def test_covers_every_view_the_interface_has(self, demo_session: Session) -> None:
        planned = planned_requests(demo_session, "demo")
        for required in (
            "/skills/graph",
            "/skills/positions?profile=demo",
            "/deliverables?profile=demo",
            "/market/gaps?profile=demo",
            "/postings",
            "/agent-runs",
            "/periodic-reviews?profile=demo",
            "/cases?profile=demo",
        ):
            assert required in planned

    def test_covers_every_scenario_the_case_view_offers(
        self, demo_session: Session
    ) -> None:
        planned = planned_requests(demo_session, "demo")
        for scenario in ("base", "pessimistic", "optimistic"):
            assert f"/cases/1?profile=demo&scenario={scenario}" in planned

    def test_covers_every_evidence_level_the_selector_offers(
        self, demo_session: Session
    ) -> None:
        planned = planned_requests(demo_session, "demo")
        for level in (2, 3, 4, 5):
            assert f"/evidence-cv?min_level={level}&profile=demo" in planned

    def test_is_deduplicated_and_stable(self, demo_session: Session) -> None:
        planned = planned_requests(demo_session, "demo")
        assert len(planned) == len(set(planned))
        assert planned == sorted(planned)


class TestGeneration:
    def test_records_every_planned_request(
        self, demo_session: Session, tmp_path: Path
    ) -> None:
        result = generate(demo_session, tmp_path / "snapshot.json", "demo")
        assert result.failures == {}
        assert result.entries == len(planned_requests(demo_session, "demo"))

    def test_writes_valid_json_with_a_generation_date(
        self, demo_session: Session, tmp_path: Path
    ) -> None:
        path = tmp_path / "snapshot.json"
        generate(demo_session, path, "demo")
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["read_only"] is True
        assert payload["profile"] == "demo"
        assert payload["generated_at"]
        assert payload["responses"]["/skills/graph"]["is_acyclic"] is True

    def test_refuses_a_profile_that_is_not_a_demo(
        self, demo_session: Session, tmp_path: Path
    ) -> None:
        """The guard that stops real data reaching a public URL."""
        from app.services.seeding import ensure_owner_profile

        ensure_owner_profile(demo_session, "owner", "Owner")
        demo_session.flush()
        with pytest.raises(ValueError, match="not a demonstration profile"):
            generate(demo_session, tmp_path / "s.json", "owner")

    def test_refuses_an_unknown_profile(
        self, demo_session: Session, tmp_path: Path
    ) -> None:
        with pytest.raises(ValueError, match="unknown profile"):
            generate(demo_session, tmp_path / "s.json", "nobody")

    def test_strips_other_profiles_from_the_published_responses(
        self, demo_session: Session, tmp_path: Path
    ) -> None:
        """Privacy, and a broken profile selector, in one fix.

        A visitor offered "Owner" in the dropdown could select it, and every
        request after that would be a key the snapshot does not hold.
        """
        from app.services.seeding import ensure_owner_profile

        ensure_owner_profile(demo_session, "owner", "Owner")
        demo_session.flush()

        path = tmp_path / "snapshot.json"
        generate(demo_session, path, "demo")
        payload = json.loads(path.read_text(encoding="utf-8"))

        assert [p["code"] for p in payload["responses"]["/profiles"]] == ["demo"]
        assert [p["code"] for p in payload["responses"]["/meta"]["profiles"]] == ["demo"]

    def test_every_recorded_response_is_a_200_body(
        self, demo_session: Session, tmp_path: Path
    ) -> None:
        result = generate(demo_session, tmp_path / "s.json", "demo")
        payload = json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))
        assert len(payload["responses"]) == result.entries
        assert all(value is not None for value in payload["responses"].values())


class TestCommittedSnapshot:
    """The file that is actually published."""

    @pytest.fixture
    def committed(self) -> dict:
        path = REPO_FRONTEND / "public" / "snapshot.json"
        if not path.exists():
            pytest.skip("no snapshot committed yet; run `make snapshot`")
        return json.loads(path.read_text(encoding="utf-8"))

    def test_is_a_demo_profile(self, committed: dict) -> None:
        assert committed["profile"] == "demo"
        assert committed["read_only"] is True

    def test_publishes_no_other_profile(self, committed: dict) -> None:
        codes = {p["code"] for p in committed["responses"]["/profiles"]}
        assert codes == {"demo"}

    def test_holds_the_views_the_site_needs(self, committed: dict) -> None:
        responses = committed["responses"]
        for required in (
            "/skills/graph",
            "/skills/positions?profile=demo",
            "/cases?profile=demo",
            "/market/gaps?profile=demo",
            "/quota-status?profile=demo&quarters_back=8",
            "/evidence-cv?min_level=3&profile=demo",
        ):
            assert required in responses, f"the published snapshot is missing {required}"


class TestNetlifyConfiguration:
    @pytest.fixture
    def config(self) -> str:
        path = REPO_FRONTEND.parent / "netlify.toml"
        if not path.exists():
            pytest.skip("netlify.toml is absent")
        return path.read_text(encoding="utf-8")

    def test_builds_in_static_mode(self, config: str) -> None:
        # Without this the published site would try to reach localhost:8000.
        assert 'VITE_STATIC_SNAPSHOT = "true"' in config

    def test_serves_the_single_page_application_on_every_path(self, config: str) -> None:
        assert 'to = "/index.html"' in config
        assert "status = 200" in config
