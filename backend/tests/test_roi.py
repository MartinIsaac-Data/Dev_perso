"""The financial engine.

Tested against a model small enough to compute by hand, because a discounted
cash flow is exactly the kind of code that produces a plausible wrong answer.
The reference model below is:

    discount rate 10%
    year 0   cost     1,000
    year 1   benefit    600
    year 2   benefit    600

    NPV = -1000 + 600/1.1 + 600/1.21
        = -1000 + 545.454545… + 495.867768…
        =    41.32

    PV of benefits = 1,041.32,  BCR = 1.041

    Discounted payback: cumulative is -1000, then -454.55, then +41.32,
    so it crosses during year 2, 454.545…/495.868… = 0.9167 of the way
    through it: 1.92 years.

Every number in this docstring is asserted below. If the engine changes, one
of these fails and the docstring is the specification to check it against.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models import Assumption, BusinessCase, RoiLine, RoiModel
from app.services import roi


def make_case(session: Session, profile_id: int, currency: str = "EUR") -> BusinessCase:
    case = BusinessCase(
        profile_id=profile_id,
        title="Reference case",
        symptom="A symptom.",
        currency=currency,
        opened_on=date(2026, 1, 1),
    )
    session.add(case)
    session.flush()
    return case


def add_assumption(
    session: Session,
    case: BusinessCase,
    code: str,
    base: str,
    low: str | None = None,
    high: str | None = None,
    confidence: str = "medium",
    source: str | None = "a source",
) -> Assumption:
    assumption = Assumption(
        case_id=case.id,
        code=code,
        label=code.replace("_", " "),
        base_value=Decimal(base),
        low_value=Decimal(low) if low is not None else None,
        high_value=Decimal(high) if high is not None else None,
        confidence=confidence,
        source=source,
    )
    session.add(assumption)
    session.flush()
    return assumption


def add_line(
    session: Session,
    model: RoiModel,
    kind: str,
    year: int,
    assumption: Assumption,
    quantity: str = "1",
    category: str | None = None,
) -> RoiLine:
    line = RoiLine(
        roi_model_id=model.id,
        kind=kind,
        category=category or ("build" if kind == "cost" else "loss_avoidance"),
        label=f"{kind} y{year}",
        year_index=year,
        amount_assumption_id=assumption.id,
        quantity=Decimal(quantity),
    )
    session.add(line)
    session.flush()
    return line


@pytest.fixture
def reference_model(seeded_session: Session) -> RoiModel:
    """The model in the module docstring."""
    from app.models import Profile

    profile = Profile(code="t", display_name="T")
    seeded_session.add(profile)
    seeded_session.flush()

    case = make_case(seeded_session, profile.id)
    cost = add_assumption(seeded_session, case, "cost", "1000", "800", "1500")
    benefit = add_assumption(seeded_session, case, "benefit", "600", "300", "900")

    model = RoiModel(
        case_id=case.id, version=1, horizon_years=3, discount_rate=Decimal("0.10")
    )
    seeded_session.add(model)
    seeded_session.flush()

    add_line(seeded_session, model, "cost", 0, cost)
    add_line(seeded_session, model, "benefit", 1, benefit)
    add_line(seeded_session, model, "benefit", 2, benefit)
    seeded_session.flush()
    return model


class TestScenarioRule:
    """The unfavourable end depends on whether it is a cost or a benefit."""

    @pytest.fixture
    def assumption(self, seeded_session: Session) -> Assumption:
        from app.models import Profile

        profile = Profile(code="s", display_name="S")
        seeded_session.add(profile)
        seeded_session.flush()
        case = make_case(seeded_session, profile.id)
        return add_assumption(seeded_session, case, "a", "100", "60", "150")

    def test_base_always_takes_the_base_value(self, assumption: Assumption) -> None:
        for favourable in (True, False):
            value = roi.assumption_value(
                assumption, "base", favourable_when_high=favourable
            )
            assert value == Decimal("100")

    def test_pessimistic_cost_takes_the_high_end(self, assumption: Assumption) -> None:
        # A cost is favourable when low, so pessimistic means it costs more.
        assert roi.assumption_value(
            assumption, "pessimistic", favourable_when_high=False
        ) == Decimal("150")

    def test_pessimistic_benefit_takes_the_low_end(self, assumption: Assumption) -> None:
        assert roi.assumption_value(
            assumption, "pessimistic", favourable_when_high=True
        ) == Decimal("60")

    def test_optimistic_cost_takes_the_low_end(self, assumption: Assumption) -> None:
        assert roi.assumption_value(
            assumption, "optimistic", favourable_when_high=False
        ) == Decimal("60")

    def test_optimistic_benefit_takes_the_high_end(self, assumption: Assumption) -> None:
        assert roi.assumption_value(
            assumption, "optimistic", favourable_when_high=True
        ) == Decimal("150")

    def test_missing_bounds_fall_back_to_base_not_zero(
        self, seeded_session: Session
    ) -> None:
        """A point estimate must not collapse a scenario to nothing."""
        from app.models import Profile

        profile = Profile(code="p", display_name="P")
        seeded_session.add(profile)
        seeded_session.flush()
        case = make_case(seeded_session, profile.id)
        point = add_assumption(seeded_session, case, "point", "250")

        for scenario in roi.SCENARIOS:
            for favourable in (True, False):
                value = roi.assumption_value(
                    point, scenario, favourable_when_high=favourable
                )
                assert value == Decimal("250")


class TestDiscountedCashFlow:
    def test_npv_matches_the_hand_computed_reference(
        self, reference_model: RoiModel
    ) -> None:
        assert roi.compute(reference_model, "base").npv == Decimal("41.32")

    def test_year_zero_is_not_discounted(self, reference_model: RoiModel) -> None:
        result = roi.compute(reference_model, "base")
        year_zero = next(f for f in result.flows if f.year_index == 0)
        # The whole 1,000 must appear undiscounted in the PV of costs.
        assert result.total_cost_pv == Decimal("1000.00")
        assert year_zero.costs == Decimal("1000.00")

    def test_present_value_of_benefits(self, reference_model: RoiModel) -> None:
        assert roi.compute(reference_model, "base").total_benefit_pv == Decimal("1041.32")

    def test_nominal_totals_ignore_discounting(self, reference_model: RoiModel) -> None:
        result = roi.compute(reference_model, "base")
        assert result.total_benefit_nominal == Decimal("1200.00")
        assert result.total_cost_nominal == Decimal("1000.00")

    def test_benefit_cost_ratio(self, reference_model: RoiModel) -> None:
        assert roi.compute(reference_model, "base").benefit_cost_ratio == Decimal("1.041")

    def test_quantity_multiplies_the_amount(
        self, seeded_session: Session, reference_model: RoiModel
    ) -> None:
        line = next(x for x in reference_model.lines if x.kind == "cost")
        line.quantity = Decimal("3")
        seeded_session.flush()
        result = roi.compute(reference_model, "base")
        assert result.total_cost_nominal == Decimal("3000.00")

    def test_a_zero_rate_leaves_flows_undiscounted(
        self, seeded_session: Session, reference_model: RoiModel
    ) -> None:
        reference_model.discount_rate = Decimal("0")
        seeded_session.flush()
        result = roi.compute(reference_model, "base")
        assert result.npv == Decimal("200.00")

    def test_scenarios_are_ordered(self, reference_model: RoiModel) -> None:
        results = roi.compare_scenarios(reference_model)
        assert results["pessimistic"].npv < results["base"].npv < results["optimistic"].npv

    def test_pessimistic_uses_high_cost_and_low_benefit(
        self, reference_model: RoiModel
    ) -> None:
        result = roi.compute(reference_model, "pessimistic")
        assert result.total_cost_nominal == Decimal("1500.00")
        assert result.total_benefit_nominal == Decimal("600.00")  # 300 x 2 years

    def test_benefit_cost_ratio_is_none_without_costs(
        self, seeded_session: Session, reference_model: RoiModel
    ) -> None:
        # A model with no costs is a modelling error; returning a number
        # would hide it behind an impressive-looking ratio.
        for line in list(reference_model.lines):
            if line.kind == "cost":
                seeded_session.delete(line)
        seeded_session.flush()
        seeded_session.refresh(reference_model)
        assert roi.compute(reference_model, "base").benefit_cost_ratio is None


class TestPayback:
    def test_interpolates_within_the_crossing_year(
        self, reference_model: RoiModel
    ) -> None:
        # Cumulative is -1000, -454.55, +41.32: it crosses 91.67% of the way
        # through year 2.
        assert roi.compute(reference_model, "base").payback_years == Decimal("1.92")

    def test_none_when_it_never_pays_back(self, reference_model: RoiModel) -> None:
        result = roi.compute(reference_model, "pessimistic")
        assert result.npv < 0
        # Not the horizon length, which would read as "pays back in year 3".
        assert result.payback_years is None

    def test_zero_when_positive_from_the_outset(self, seeded_session: Session) -> None:
        from app.models import Profile

        profile = Profile(code="z", display_name="Z")
        seeded_session.add(profile)
        seeded_session.flush()
        case = make_case(seeded_session, profile.id)
        benefit = add_assumption(seeded_session, case, "b", "500")
        model = RoiModel(
            case_id=case.id, version=1, horizon_years=2, discount_rate=Decimal("0.1")
        )
        seeded_session.add(model)
        seeded_session.flush()
        add_line(seeded_session, model, "benefit", 0, benefit)
        seeded_session.flush()

        assert roi.compute(model, "base").payback_years == Decimal("0")


class TestTornado:
    def test_ranked_by_swing_descending(self, reference_model: RoiModel) -> None:
        rows = roi.tornado(reference_model)
        swings = [row.swing for row in rows]
        assert swings == sorted(swings, reverse=True)

    def test_covers_every_assumption_used_by_a_line(
        self, reference_model: RoiModel
    ) -> None:
        assert {row.code for row in roi.tornado(reference_model)} == {"cost", "benefit"}

    def test_ignores_assumptions_no_line_references(
        self, seeded_session: Session, reference_model: RoiModel
    ) -> None:
        # An assumption that sizes a cause branch but no cash flow cannot move
        # the NPV; listing it at zero swing would bury the ones that can.
        case = seeded_session.get(BusinessCase, reference_model.case_id)
        add_assumption(seeded_session, case, "unused", "9999", "1", "99999")
        seeded_session.flush()
        assert "unused" not in {row.code for row in roi.tornado(reference_model)}

    def test_varies_one_assumption_and_holds_the_rest_at_base(
        self, reference_model: RoiModel
    ) -> None:
        rows = {row.code: row for row in roi.tornado(reference_model)}
        base_npv = roi.compute(reference_model, "base").npv

        # Cost at its low bound of 800 improves NPV by exactly 200 against a
        # base of 1000, with benefits untouched.
        assert rows["cost"].npv_at_low == base_npv + Decimal("200.00")
        assert rows["cost"].npv_at_high == base_npv - Decimal("500.00")

    def test_swing_is_the_full_range(self, reference_model: RoiModel) -> None:
        rows = {row.code: row for row in roi.tornado(reference_model)}
        assert rows["cost"].swing == Decimal("700.00")

    def test_detects_an_assumption_that_flips_the_decision(
        self, reference_model: RoiModel
    ) -> None:
        # Base NPV is +41.32; the cost's high bound takes it to -458.68.
        rows = {row.code: row for row in roi.tornado(reference_model)}
        assert rows["cost"].flips_the_decision
        assert rows["cost"].npv_at_high < 0 < rows["cost"].npv_at_low

    def test_point_estimate_has_no_range(self, seeded_session: Session) -> None:
        from app.models import Profile

        profile = Profile(code="pe", display_name="PE")
        seeded_session.add(profile)
        seeded_session.flush()
        case = make_case(seeded_session, profile.id)
        fixed = add_assumption(seeded_session, case, "fixed", "100")
        model = RoiModel(
            case_id=case.id, version=1, horizon_years=2, discount_rate=Decimal("0.1")
        )
        seeded_session.add(model)
        seeded_session.flush()
        add_line(seeded_session, model, "cost", 0, fixed)
        seeded_session.flush()

        row = roi.tornado(model)[0]
        assert not row.has_range
        assert row.swing == Decimal("0")


class TestFragility:
    def test_flags_the_decision_flipping_assumption(
        self, reference_model: RoiModel
    ) -> None:
        report = roi.fragility(reference_model)
        assert {row.code for row in report.decision_flipping} == {"cost", "benefit"}
        assert "depends on" in report.headline

    def test_flags_unsourced_assumptions(
        self, seeded_session: Session, reference_model: RoiModel
    ) -> None:
        cost = next(
            x.amount_assumption for x in reference_model.lines if x.kind == "cost"
        )
        cost.source = None
        seeded_session.flush()
        assert "cost" in {row.code for row in roi.fragility(reference_model).unsourced}

    def test_flags_low_confidence_among_the_largest_swings(
        self, seeded_session: Session, reference_model: RoiModel
    ) -> None:
        benefit = next(
            x.amount_assumption for x in reference_model.lines if x.kind == "benefit"
        )
        benefit.confidence = "low"
        seeded_session.flush()
        report = roi.fragility(reference_model)
        assert "benefit" in {row.code for row in report.low_confidence_high_impact}

    def test_separates_combination_failure_from_single_point_failure(
        self, seeded_session: Session, reference_model: RoiModel
    ) -> None:
        """A case no single assumption breaks, but the pessimistic case does.

        The distinction matters: one flipping assumption is a research task,
        while a case that survives each assumption alone but fails when they
        all land badly is a question about whether those risks are correlated.
        """
        # Widen the base so no single bound crosses zero, but both together do.
        cost = next(x.amount_assumption for x in reference_model.lines if x.kind == "cost")
        benefit = next(
            x.amount_assumption for x in reference_model.lines if x.kind == "benefit"
        )
        cost.base_value, cost.low_value, cost.high_value = (
            Decimal("1000"),
            Decimal("950"),
            Decimal("1150"),
        )
        benefit.base_value, benefit.low_value, benefit.high_value = (
            Decimal("700"),
            Decimal("620"),
            Decimal("780"),
        )
        seeded_session.flush()

        report = roi.fragility(reference_model)
        assert report.base_npv > 0
        assert not report.decision_flipping
        assert report.pessimistic_npv <= 0
        assert report.only_fails_in_combination
        assert "correlated" in report.headline or "independent" in report.headline

    def test_robust_case_says_so(
        self, seeded_session: Session, reference_model: RoiModel
    ) -> None:
        benefit = next(
            x.amount_assumption for x in reference_model.lines if x.kind == "benefit"
        )
        benefit.base_value, benefit.low_value, benefit.high_value = (
            Decimal("5000"),
            Decimal("4000"),
            Decimal("6000"),
        )
        seeded_session.flush()
        report = roi.fragility(reference_model)
        assert report.survives_pessimistic
        assert not report.decision_flipping
        assert "holds across every stated range" in report.headline


class TestDemoCaseEconomics:
    """The shipped example must be arguable, not obviously wonderful.

    A demonstration case with a benefit-cost ratio of 5 and a payback inside a
    year argues against its own method: no CFO would believe it, and the review
    board scoring it 5.5 on ROI credibility would make no sense.
    """

    @pytest.fixture
    def demo_model(self, demo_session: Session) -> RoiModel:
        from sqlalchemy import select

        return roi.load_model(demo_session, demo_session.scalar(select(RoiModel.id)))

    def test_base_case_is_positive_but_not_absurd(self, demo_model: RoiModel) -> None:
        result = roi.compute(demo_model, "base")
        assert result.npv > 0
        assert Decimal("1.2") < result.benefit_cost_ratio < Decimal("3.0")

    def test_base_case_does_not_pay_back_within_a_year(
        self, demo_model: RoiModel
    ) -> None:
        payback = roi.compute(demo_model, "base").payback_years
        assert payback is not None
        assert payback > Decimal("1")

    def test_the_pessimistic_case_genuinely_fails(self, demo_model: RoiModel) -> None:
        # Without this the review board's "conditionally supportable" verdict
        # would be inconsistent with its own numbers.
        result = roi.compute(demo_model, "pessimistic")
        assert result.npv < 0
        assert result.payback_years is None

    def test_run_licence_and_change_costs_are_all_present(
        self, demo_model: RoiModel
    ) -> None:
        categories = {line.category for line in demo_model.lines}
        assert {"build", "run", "license", "change_management"} <= categories

    def test_costs_are_a_meaningful_share_of_benefits(
        self, demo_model: RoiModel
    ) -> None:
        result = roi.compute(demo_model, "base")
        share = result.total_cost_pv / result.total_benefit_pv
        assert share > Decimal("0.3"), "costs this small mean something was left out"
