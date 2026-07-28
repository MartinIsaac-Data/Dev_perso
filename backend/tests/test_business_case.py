"""Cause tree computation, reconciliation, and the Business Case Lab API.

The reconciliation tests are the ones that matter. A tool that quietly closed
the gap between the bottom-up total and the figure the client asserted — by
scaling the tree, or by adding an "other" branch — would remove the single
most instructive number in the whole exercise, and it would do it invisibly.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BusinessCase, CauseDriver, CauseNode, Profile
from app.services import business_case as bc
from tests.test_roi import add_assumption, make_case


@pytest.fixture
def tree_case(seeded_session: Session) -> BusinessCase:
    """A two-branch tree whose arithmetic is obvious.

        root A
          leaf A1 = 10 x 5   =  50
          leaf A2 = 7        =   7
        root B
          leaf B1 = 3 x 4    =  12
                            total 69

    Claimed loss is 100, so 31 (31%) is unexplained.
    """
    profile = Profile(code="tc", display_name="TC")
    seeded_session.add(profile)
    seeded_session.flush()

    case = make_case(seeded_session, profile.id)
    case.claimed_annual_loss = Decimal("100")
    ten = add_assumption(seeded_session, case, "ten", "10", "8", "14")
    five = add_assumption(seeded_session, case, "five", "5", "4", "6")
    seven = add_assumption(seeded_session, case, "seven", "7")
    three = add_assumption(seeded_session, case, "three", "3", "2", "5")
    four = add_assumption(seeded_session, case, "four", "4", "3", "4")

    def node(label: str, parent: CauseNode | None, ordinal: int = 0) -> CauseNode:
        created = CauseNode(
            case_id=case.id,
            parent_id=parent.id if parent else None,
            label=label,
            ordinal=ordinal,
        )
        seeded_session.add(created)
        seeded_session.flush()
        return created

    root_a = node("A", None, 0)
    root_b = node("B", None, 1)
    leaf_a1 = node("A1", root_a, 0)
    leaf_a2 = node("A2", root_a, 1)
    leaf_b1 = node("B1", root_b, 0)

    for target, assumptions in (
        (leaf_a1, [ten, five]),
        (leaf_a2, [seven]),
        (leaf_b1, [three, four]),
    ):
        for index, assumption in enumerate(assumptions):
            seeded_session.add(
                CauseDriver(
                    cause_node_id=target.id, assumption_id=assumption.id, ordinal=index
                )
            )
    seeded_session.flush()
    return case


class TestCauseTree:
    def test_leaf_is_the_product_of_its_drivers(
        self, seeded_session: Session, tree_case: BusinessCase
    ) -> None:
        tree = bc.build_cause_tree(seeded_session, tree_case, "base")
        leaves = {leaf.label: leaf.value for leaf in tree.ranked_leaves}
        assert leaves["A1"] == Decimal("50")
        assert leaves["A2"] == Decimal("7")
        assert leaves["B1"] == Decimal("12")

    def test_internal_node_is_the_sum_of_its_children(
        self, seeded_session: Session, tree_case: BusinessCase
    ) -> None:
        tree = bc.build_cause_tree(seeded_session, tree_case, "base")
        roots = {root.label: root.value for root in tree.roots}
        assert roots["A"] == Decimal("57")
        assert roots["B"] == Decimal("12")

    def test_total_is_the_sum_of_the_roots(
        self, seeded_session: Session, tree_case: BusinessCase
    ) -> None:
        assert bc.build_cause_tree(seeded_session, tree_case, "base").total == Decimal("69")

    def test_leaves_are_ranked_by_value(
        self, seeded_session: Session, tree_case: BusinessCase
    ) -> None:
        tree = bc.build_cause_tree(seeded_session, tree_case, "base")
        assert [leaf.label for leaf in tree.ranked_leaves] == ["A1", "B1", "A2"]

    def test_an_unquantified_leaf_contributes_nothing(
        self, seeded_session: Session, tree_case: BusinessCase
    ) -> None:
        # Zero, not one: an empty product must not silently add a unit.
        empty = CauseNode(case_id=tree_case.id, parent_id=None, label="C", ordinal=2)
        seeded_session.add(empty)
        seeded_session.flush()
        tree = bc.build_cause_tree(seeded_session, tree_case, "base")
        assert next(r for r in tree.roots if r.label == "C").value == Decimal("0")
        assert tree.total == Decimal("69")

    def test_drivers_on_an_internal_node_are_ignored(
        self, seeded_session: Session, tree_case: BusinessCase
    ) -> None:
        """Otherwise the node would count both its own product and its children."""
        root_a = seeded_session.scalar(
            select(CauseNode).where(
                CauseNode.case_id == tree_case.id, CauseNode.label == "A"
            )
        )
        seven = seeded_session.scalar(
            select(bc.Assumption).where(bc.Assumption.code == "seven")
        )
        seeded_session.add(
            CauseDriver(cause_node_id=root_a.id, assumption_id=seven.id, ordinal=0)
        )
        seeded_session.flush()
        tree = bc.build_cause_tree(seeded_session, tree_case, "base")
        assert next(r for r in tree.roots if r.label == "A").value == Decimal("57")

    def test_a_cause_tree_is_unfavourable_when_high(
        self, seeded_session: Session, tree_case: BusinessCase
    ) -> None:
        # Losses: the pessimistic case takes the top of every range.
        pessimistic = bc.build_cause_tree(seeded_session, tree_case, "pessimistic")
        optimistic = bc.build_cause_tree(seeded_session, tree_case, "optimistic")
        # A1 pessimistic = 14 x 6 = 84, optimistic = 8 x 4 = 32.
        assert next(
            leaf.value for leaf in pessimistic.ranked_leaves if leaf.label == "A1"
        ) == Decimal("84")
        assert next(
            leaf.value for leaf in optimistic.ranked_leaves if leaf.label == "A1"
        ) == Decimal("32")
        assert pessimistic.total > optimistic.total

    def test_depth_is_recorded(
        self, seeded_session: Session, tree_case: BusinessCase
    ) -> None:
        tree = bc.build_cause_tree(seeded_session, tree_case, "base")
        assert all(root.depth == 0 for root in tree.roots)
        assert all(child.depth == 1 for root in tree.roots for child in root.children)


class TestReconciliation:
    def test_reports_the_gap_without_closing_it(
        self, seeded_session: Session, tree_case: BusinessCase
    ) -> None:
        reconciliation = bc.build_cause_tree(
            seeded_session, tree_case, "base"
        ).reconciliation
        assert reconciliation.bottom_up_total == Decimal("69")
        assert reconciliation.claimed_annual_loss == Decimal("100")
        assert reconciliation.gap == Decimal("31")
        assert reconciliation.gap_ratio == Decimal("0.3100")
        assert "unaccounted for" in reconciliation.verdict

    def test_says_so_when_the_tree_matches(
        self, seeded_session: Session, tree_case: BusinessCase
    ) -> None:
        tree_case.claimed_annual_loss = Decimal("70")
        seeded_session.flush()
        verdict = bc.build_cause_tree(
            seeded_session, tree_case, "base"
        ).reconciliation.verdict
        assert "within 5%" in verdict

    def test_flags_probable_double_counting(
        self, seeded_session: Session, tree_case: BusinessCase
    ) -> None:
        tree_case.claimed_annual_loss = Decimal("40")
        seeded_session.flush()
        reconciliation = bc.build_cause_tree(
            seeded_session, tree_case, "base"
        ).reconciliation
        assert reconciliation.gap < 0
        assert "double-counting" in reconciliation.verdict

    def test_no_claim_means_nothing_to_reconcile(
        self, seeded_session: Session, tree_case: BusinessCase
    ) -> None:
        tree_case.claimed_annual_loss = None
        seeded_session.flush()
        reconciliation = bc.build_cause_tree(
            seeded_session, tree_case, "base"
        ).reconciliation
        assert reconciliation.gap is None
        assert reconciliation.gap_ratio is None

    def test_the_demo_gap_is_preserved(self, demo_session: Session) -> None:
        case = demo_session.scalar(select(BusinessCase))
        reconciliation = bc.build_cause_tree(
            demo_session, case, "base"
        ).reconciliation
        assert reconciliation.bottom_up_total == Decimal("3492608.000")
        assert Decimal("0.15") < reconciliation.gap_ratio < Decimal("0.20")


class TestAssumptionAudit:
    def test_finds_assumptions_nothing_references(
        self, seeded_session: Session, tree_case: BusinessCase
    ) -> None:
        # More than housekeeping: an orphan is often a cost the author meant
        # to include and forgot.
        add_assumption(seeded_session, tree_case, "orphan", "500")
        seeded_session.flush()
        audit = bc.audit_assumptions(seeded_session, tree_case)
        assert audit.unused == ["orphan"]

    def test_finds_point_estimates(
        self, seeded_session: Session, tree_case: BusinessCase
    ) -> None:
        assert "seven" in bc.audit_assumptions(seeded_session, tree_case).point_estimates

    def test_finds_unsourced_assumptions(
        self, seeded_session: Session, tree_case: BusinessCase
    ) -> None:
        assumption = seeded_session.scalar(
            select(bc.Assumption).where(bc.Assumption.code == "ten")
        )
        assumption.source = None
        seeded_session.flush()
        assert "ten" in bc.audit_assumptions(seeded_session, tree_case).unsourced

    def test_the_demo_case_is_fully_sourced(self, demo_session: Session) -> None:
        case = demo_session.scalar(select(BusinessCase))
        audit = bc.audit_assumptions(demo_session, case)
        assert audit.unsourced == []
        assert audit.unused == []
        assert audit.low_confidence, "the example must admit its weak points"


class TestCasesApi:
    def test_lists_cases_with_computed_headlines(self, client: TestClient) -> None:
        rows = client.get("/cases").json()
        assert len(rows) == 1
        case = rows[0]
        assert Decimal(case["bottom_up_total"]) == Decimal("3492608.000")
        assert case["base_npv"] is not None
        assert case["open_challenges"] == 8

    def test_case_detail_carries_tree_solution_and_reviews(
        self, client: TestClient
    ) -> None:
        case = client.get("/cases/1").json()
        assert case["cause_tree"]["roots"]
        assert case["solution"]["architecture"]
        assert case["solution"]["kpis"]
        assert case["reviews"]
        assert case["audit"]["total"] > 0

    def test_scenario_changes_the_tree(self, client: TestClient) -> None:
        base = client.get("/cases/1/cause-tree?scenario=base").json()
        pessimistic = client.get("/cases/1/cause-tree?scenario=pessimistic").json()
        assert Decimal(pessimistic["total"]) > Decimal(base["total"])

    def test_unknown_scenario_is_422(self, client: TestClient) -> None:
        assert client.get("/cases/1/cause-tree?scenario=hopeful").status_code == 422

    def test_scenarios_endpoint_returns_all_three(self, client: TestClient) -> None:
        body = client.get("/cases/1/roi/scenarios").json()
        assert set(body) == {"pessimistic", "base", "optimistic"}
        assert Decimal(body["pessimistic"]["npv"]) < Decimal(body["base"]["npv"])
        assert body["pessimistic"]["is_positive"] is False

    def test_tornado_is_ranked(self, client: TestClient) -> None:
        rows = client.get("/cases/1/roi/tornado").json()
        swings = [Decimal(row["swing"]) for row in rows]
        assert swings == sorted(swings, reverse=True)
        assert rows[0]["code"] == "benefit_stockout"

    def test_fragility_explains_itself(self, client: TestClient) -> None:
        body = client.get("/cases/1/roi/fragility").json()
        assert body["survives_pessimistic"] is False
        assert body["only_fails_in_combination"] is True
        assert body["headline"]

    def test_reviews_order_challenges_by_severity(self, client: TestClient) -> None:
        reviews = client.get("/cases/1/reviews").json()
        severities = [c["severity"] for c in reviews[0]["challenges"]]
        rank = {"blocking": 0, "major": 1, "minor": 2}
        assert [rank[s] for s in severities] == sorted(rank[s] for s in severities)

    def test_challenges_name_the_assumption_they_attack(
        self, client: TestClient
    ) -> None:
        reviews = client.get("/cases/1/reviews").json()
        pinned = [
            c for c in reviews[0]["challenges"] if c["target_assumption_code"]
        ]
        assert pinned
        assert "benefit_planner_time" in {c["target_assumption_code"] for c in pinned}

    def test_answering_a_challenge_closes_it(self, client: TestClient) -> None:
        reviews = client.get("/cases/1/reviews").json()
        challenge = reviews[0]["challenges"][0]
        assert challenge["resolved_on"] is None

        response = client.post(
            f"/cases/1/challenges/{challenge['id']}/response",
            json={"response": "Removed from the base case.", "resolved_on": "2026-08-01"},
        )
        assert response.status_code == 200
        assert response.json()["resolved_on"] == "2026-08-01"

        after = client.get("/cases").json()[0]
        assert after["open_challenges"] == 7

    def test_revising_an_assumption_moves_the_npv(self, client: TestClient) -> None:
        before = Decimal(client.get("/cases/1/roi").json()["npv"])
        response = client.patch(
            "/cases/1/assumptions/benefit_planner_time",
            json={"base_value": "0", "low_value": "0", "high_value": "0"},
        )
        assert response.status_code == 200
        after = Decimal(client.get("/cases/1/roi").json()["npv"])
        assert after < before

    def test_inverted_bounds_are_refused_with_a_readable_message(
        self, client: TestClient
    ) -> None:
        response = client.patch(
            "/cases/1/assumptions/build_cost", json={"low_value": "9999999"}
        )
        assert response.status_code == 422
        assert "low_value" in response.json()["detail"]

    def test_unknown_assumption_lists_what_exists(self, client: TestClient) -> None:
        response = client.patch("/cases/1/assumptions/nonsense", json={"label": "x"})
        assert response.status_code == 422
        assert "build_cost" in response.json()["detail"]

    def test_deleting_a_referenced_assumption_is_a_conflict(
        self, client: TestClient
    ) -> None:
        response = client.delete("/cases/1/assumptions/build_cost")
        assert response.status_code == 409

    def test_creating_a_case_starts_empty(self, client: TestClient) -> None:
        response = client.post(
            "/cases",
            json={
                "title": "New case",
                "symptom": "They say something costs a lot.",
                "claimed_annual_loss": "1000000",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert Decimal(body["bottom_up_total"]) == 0
        assert body["base_npv"] is None

    def test_a_new_roi_model_gets_the_next_version(self, client: TestClient) -> None:
        response = client.post(
            "/cases/1/roi-models", json={"horizon_years": 5, "discount_rate": "0.15"}
        )
        assert response.status_code == 201
        assert response.json()["version"] == 2

    def test_a_case_without_a_roi_model_says_so(self, client: TestClient) -> None:
        created = client.post(
            "/cases", json={"title": "Bare", "symptom": "Nothing yet."}
        ).json()
        response = client.get(f"/cases/{created['id']}/roi")
        assert response.status_code == 404
        assert "no ROI model" in response.json()["detail"]

    def test_adding_a_cause_branch_changes_the_total(self, client: TestClient) -> None:
        before = Decimal(client.get("/cases/1/cause-tree").json()["total"])
        response = client.post(
            "/cases/1/cause-nodes",
            json={
                "label": "Customer credit notes for short deliveries",
                "driver_codes": ["expiry_writeoff"],
            },
        )
        assert response.status_code == 201
        assert Decimal(response.json()["total"]) > before

    def test_a_branch_citing_an_unknown_assumption_is_refused(
        self, client: TestClient
    ) -> None:
        response = client.post(
            "/cases/1/cause-nodes",
            json={"label": "Bad branch", "driver_codes": ["invented"]},
        )
        assert response.status_code == 422
        assert "invented" in response.json()["detail"]

    def test_another_profile_cannot_read_the_case(self, client: TestClient) -> None:
        assert client.get("/cases/1?profile=owner").status_code == 404


@pytest.fixture
def _unused_date() -> date:  # pragma: no cover - keeps the import honest
    return date.today()
