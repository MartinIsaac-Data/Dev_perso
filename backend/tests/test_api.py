"""End-to-end API tests.

These run against the real application — same routers, same dependencies, same
validation — pointed at a throwaway in-memory database. The point is to catch
what unit tests structurally cannot: a response model that drops a field, a
dependency that resolves the wrong profile, an exception that escapes as a 500
where it should have been a 422.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

AS_OF = "2026-07-28"


class TestMeta:
    def test_health(self, client: TestClient) -> None:
        assert client.get("/health").json() == {"status": "ok"}

    def test_meta_reports_loaded_content(self, client: TestClient) -> None:
        body = client.get("/meta").json()
        assert body["counts"]["skills"] == 83
        assert body["counts"]["skill_edges"] == 111
        assert any(p["is_demo"] for p in body["profiles"])


class TestProfileResolution:
    def test_defaults_to_the_demo_profile(self, client: TestClient) -> None:
        response = client.get("/deliverables")
        assert response.status_code == 200
        assert response.json()

    def test_unknown_profile_is_a_404_that_says_what_exists(
        self, client: TestClient
    ) -> None:
        response = client.get("/deliverables?profile=nobody")
        assert response.status_code == 404
        assert "demo" in response.json()["detail"]


class TestGraphEndpoints:
    def test_graph_is_acyclic(self, client: TestClient) -> None:
        body = client.get("/skills/graph").json()
        assert body["is_acyclic"] is True
        assert len(body["skills"]) == 83
        assert len(body["edges"]) == 111
        assert body["longest_chain"] == 8

    def test_levels_are_defined(self, client: TestClient) -> None:
        levels = client.get("/skills/levels").json()
        assert [level["level"] for level in levels] == [0, 1, 2, 3, 4, 5]
        assert all(level["definition"] for level in levels)

    def test_critical_path_names_what_it_blocks(self, client: TestClient) -> None:
        rows = client.get(f"/skills/critical-path?limit=5&as_of={AS_OF}").json()
        assert len(rows) == 5
        assert all(row["gap"] > 0 for row in rows)
        scores = [row["blocks_below_target"] for row in rows]
        assert scores == sorted(scores, reverse=True)

    def test_blocked_lists_the_unmet_prerequisites(self, client: TestClient) -> None:
        rows = client.get(f"/skills/blocked?as_of={AS_OF}").json()
        assert rows
        for row in rows:
            assert row["is_blocked"] is True
            assert row["unmet_prerequisites"]
            for prerequisite in row["unmet_prerequisites"]:
                assert prerequisite["current_level"] < prerequisite["required_level"]

    def test_decayed_is_not_empty_on_the_demo(self, client: TestClient) -> None:
        rows = client.get(f"/skills/decayed?as_of={AS_OF}").json()
        assert rows, "the demo must have something to say about decay"
        assert all(row["is_decayed"] for row in rows)

    def test_domain_filter(self, client: TestClient) -> None:
        rows = client.get("/skills/positions?domain=ai_ml").json()
        assert rows
        assert {row["domain_code"] for row in rows} == {"ai_ml"}

    def test_domain_summary_covers_every_domain(self, client: TestClient) -> None:
        summary = client.get("/skills/domains/summary").json()
        assert len(summary) == 8
        assert sum(row["skills"] for row in summary) == 83


class TestTargets:
    def test_setting_a_target_is_reflected_immediately(self, client: TestClient) -> None:
        response = client.put("/skills/rag_systems/target", json={"target_level": 5})
        assert response.status_code == 200
        assert response.json()["target_level"] == 5
        assert response.json()["gap"] == 5

    def test_unknown_skill_is_a_404(self, client: TestClient) -> None:
        response = client.put("/skills/telepathy/target", json={"target_level": 3})
        assert response.status_code == 404

    def test_out_of_range_target_is_rejected_before_the_database(
        self, client: TestClient
    ) -> None:
        response = client.put("/skills/dax/target", json={"target_level": 9})
        assert response.status_code == 422


class TestLevelChanges:
    def test_promotion_without_evidence_is_422_not_500(self, client: TestClient) -> None:
        response = client.post("/skills/microsoft_fabric/level", json={"to_level": 3})
        assert response.status_code == 422
        assert "evidence" in response.json()["detail"]

    def test_promotion_citing_unrelated_work_is_refused(self, client: TestClient) -> None:
        deliverables = client.get("/deliverables").json()
        ingestion = next(d for d in deliverables if d["title"].startswith("ERP to lakehouse"))
        response = client.post(
            "/skills/executive_communication/level",
            json={"to_level": 4, "deliverable_id": ingestion["id"]},
        )
        assert response.status_code == 422
        assert "does not exercise" in response.json()["detail"]

    def test_valid_promotion_is_recorded(self, client: TestClient) -> None:
        deliverables = client.get("/deliverables").json()
        ingestion = next(d for d in deliverables if d["title"].startswith("ERP to lakehouse"))
        response = client.post(
            "/skills/file_formats/level",
            json={"to_level": 3, "deliverable_id": ingestion["id"], "rationale": "ok"},
        )
        assert response.status_code == 201
        assert response.json()["from_level"] == 2
        assert response.json()["to_level"] == 3

    def test_downgrade_needs_no_evidence(self, client: TestClient) -> None:
        response = client.post(
            "/skills/dax/level", json={"to_level": 2, "rationale": "slipped"}
        )
        assert response.status_code == 201
        assert response.json()["deliverable_id"] is None


class TestDeliverables:
    def test_create_with_skill_links(self, client: TestClient) -> None:
        response = client.post(
            "/deliverables",
            json={
                "title": "Semantic layer for the depot model",
                "type_code": "project",
                "status": "published",
                "published_on": "2026-07-25",
                "skills": [
                    {"skill_code": "semantic_layer", "contribution": 3},
                    {"skill_code": "dax", "contribution": 2},
                ],
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert {s["skill_code"] for s in body["skills"]} == {"semantic_layer", "dax"}
        # Ordered by contribution, so the central skill leads.
        assert body["skills"][0]["skill_code"] == "semantic_layer"

    def test_published_without_a_date_is_rejected_at_the_edge(
        self, client: TestClient
    ) -> None:
        response = client.post(
            "/deliverables",
            json={"title": "No date", "type_code": "article", "status": "published"},
        )
        assert response.status_code == 422

    def test_published_before_started_is_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/deliverables",
            json={
                "title": "Time travel",
                "type_code": "article",
                "status": "published",
                "started_on": "2026-07-01",
                "published_on": "2026-06-01",
            },
        )
        assert response.status_code == 422

    def test_unknown_skill_code_is_reported_by_name(self, client: TestClient) -> None:
        response = client.post(
            "/deliverables",
            json={
                "title": "Bad link",
                "type_code": "project",
                "skills": [{"skill_code": "quantum_dax"}],
            },
        )
        assert response.status_code == 422
        assert "quantum_dax" in response.json()["detail"]

    def test_unknown_type_is_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/deliverables", json={"title": "Bad type", "type_code": "podcast"}
        )
        assert response.status_code == 422

    def test_publishing_counts_towards_the_quota(self, client: TestClient) -> None:
        before = client.get(f"/quota-status?as_of={AS_OF}&quarters_back=1").json()[0]
        articles_before = next(
            line["published"] for line in before["lines"] if line["type_code"] == "article"
        )
        client.post(
            "/deliverables",
            json={
                "title": "Partitioning strategy for small teams",
                "type_code": "article",
                "status": "published",
                "published_on": "2026-07-26",
            },
        )
        after = client.get(f"/quota-status?as_of={AS_OF}&quarters_back=1").json()[0]
        articles_after = next(
            line["published"] for line in after["lines"] if line["type_code"] == "article"
        )
        assert articles_after == articles_before + 1

    def test_patch_replaces_skill_links_wholesale(self, client: TestClient) -> None:
        created = client.post(
            "/deliverables",
            json={
                "title": "Patch me",
                "type_code": "project",
                "skills": [{"skill_code": "dax", "contribution": 3}],
            },
        ).json()
        updated = client.patch(
            f"/deliverables/{created['id']}",
            json={"skills": [{"skill_code": "sql_core", "contribution": 2}]},
        ).json()
        assert {s["skill_code"] for s in updated["skills"]} == {"sql_core"}

    def test_patch_leaves_absent_fields_untouched(self, client: TestClient) -> None:
        created = client.post(
            "/deliverables",
            json={"title": "Keep my summary", "type_code": "project", "summary": "intact"},
        ).json()
        updated = client.patch(
            f"/deliverables/{created['id']}", json={"title": "Renamed"}
        ).json()
        assert updated["title"] == "Renamed"
        assert updated["summary"] == "intact"

    def test_cannot_read_another_profiles_deliverable(self, client: TestClient) -> None:
        mine = client.get("/deliverables").json()[0]
        response = client.get(f"/deliverables/{mine['id']}?profile=owner")
        assert response.status_code == 404

    def test_deleting_evidence_is_a_conflict_not_a_crash(
        self, client: TestClient
    ) -> None:
        deliverables = client.get("/deliverables").json()
        cited = next(d for d in deliverables if d["title"].startswith("ERP to lakehouse"))
        response = client.delete(f"/deliverables/{cited['id']}")
        assert response.status_code == 409
        assert "evidence" in response.json()["detail"]


class TestQuotaEndpoint:
    def test_reports_the_silent_quarter(self, client: TestClient) -> None:
        rows = client.get(f"/quota-status?as_of={AS_OF}&quarters_back=8").json()
        q1 = next(r for r in rows if (r["year"], r["quarter"]) == (2026, 1))
        assert q1["is_silent"] is True
        assert q1["met"] is False

    def test_oldest_first(self, client: TestClient) -> None:
        rows = client.get(f"/quota-status?as_of={AS_OF}&quarters_back=5").json()
        keys = [(r["year"], r["quarter"]) for r in rows]
        assert keys == sorted(keys)

    def test_pre_trajectory_quarters_are_marked_out_of_scope(
        self, client: TestClient
    ) -> None:
        rows = client.get(f"/quota-status?as_of={AS_OF}&quarters_back=10").json()
        before = [r for r in rows if r["phase_code"] is None]
        assert before
        assert all(r["in_scope"] is False for r in before)
        # And the real finding is still reported.
        q1 = next(r for r in rows if (r["year"], r["quarter"]) == (2026, 1))
        assert q1["in_scope"] is True
        assert q1["is_silent"] is True


class TestEvidenceEndpoint:
    def test_returns_claims_with_their_artefacts(self, client: TestClient) -> None:
        rows = client.get("/evidence-cv?min_level=3").json()
        assert rows
        assert all(row["current_level"] >= 3 for row in rows)
        assert any(row["evidence"] for row in rows)

    def test_surfaces_undefensible_claims(self, client: TestClient) -> None:
        rows = client.get("/evidence-cv?min_level=3").json()
        assert any(not row["is_defensible"] for row in rows)


class TestTrajectory:
    def test_phases_are_ordered_and_one_is_current(self, client: TestClient) -> None:
        phases = client.get("/phases").json()
        assert [p["ordinal"] for p in phases] == [1, 2, 3, 4]
        assert sum(1 for p in phases if p["is_current"]) == 1

    def test_phases_carry_their_quotas(self, client: TestClient) -> None:
        phases = client.get("/phases").json()
        assert all(p["quotas"] for p in phases)

    def test_target_roles_are_listed(self, client: TestClient) -> None:
        assert len(client.get("/target-roles").json()) == 4
