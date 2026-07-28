"""ROI computation: scenarios, discounted cash flow, payback, sensitivity.

Everything here is derived. Nothing computed in this module is stored in the
normalised schema (ADR-008), because a cached NPV is a number that will
eventually disagree with the assumptions it came from — and a business case
whose headline figure contradicts its own workings is worse than one with no
headline figure at all.

Three things worth reading before the code:

**Scenarios are a rule, not stored numbers** (ADR-007). An assumption carries
`low_value`, `base_value` and `high_value`. A scenario chooses within that
range according to whether the line is a cost or a benefit: the pessimistic
case takes the *unfavourable* end, which is the high value for a cost and the
low value for a benefit. Storing three amounts per line instead would let the
base case be revised while the other two silently went stale.

**Money is Decimal, never float.** A model a CFO is meant to argue with cannot
have 0.1 + 0.2 come to 0.30000000000000004. The only place a float appears is
the discount exponent, and even there the base is Decimal.

**The tornado varies one assumption at a time.** Everything else stays at
base. That is what makes the resulting swing attributable to that assumption
rather than to some interaction, and it is the standard the review board's
"what does it look like at half that improvement" question demands.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Assumption, RoiLine, RoiModel

Scenario = Literal["pessimistic", "base", "optimistic"]
SCENARIOS: tuple[Scenario, ...] = ("pessimistic", "base", "optimistic")

ZERO = Decimal("0")


def assumption_value(
    assumption: Assumption,
    scenario: Scenario,
    *,
    favourable_when_high: bool,
) -> Decimal:
    """Pick a value from an assumption's range for one scenario.

    `favourable_when_high` says which direction is good news. A benefit is
    favourable when high; a cost is favourable when low. The pessimistic case
    always takes the unfavourable end.

    A missing bound falls back to the base value rather than to zero. An
    assumption with no stated range is a point estimate, and a point estimate
    should not silently collapse a scenario to nothing.
    """
    if scenario == "base":
        return assumption.base_value

    wants_high = (scenario == "optimistic") == favourable_when_high
    if wants_high:
        return assumption.high_value if assumption.high_value is not None else assumption.base_value
    return assumption.low_value if assumption.low_value is not None else assumption.base_value


def line_amount(
    line: RoiLine,
    scenario: Scenario,
    overrides: dict[int, Decimal] | None = None,
) -> Decimal:
    """Signed contribution of one line: negative for costs, positive for benefits.

    `overrides` forces a specific value for named assumptions, which is how
    the tornado holds one assumption at an extreme while everything else stays
    at base.
    """
    if overrides is not None and line.amount_assumption_id in overrides:
        value = overrides[line.amount_assumption_id]
    else:
        value = assumption_value(
            line.amount_assumption,
            scenario,
            favourable_when_high=(line.kind == "benefit"),
        )
    amount = value * line.quantity
    return amount if line.kind == "benefit" else -amount


@dataclass(frozen=True)
class YearFlow:
    year_index: int
    costs: Decimal
    benefits: Decimal

    @property
    def net(self) -> Decimal:
        return self.benefits - self.costs


@dataclass(frozen=True)
class RoiResult:
    scenario: Scenario
    currency: str
    discount_rate: Decimal
    horizon_years: int
    flows: list[YearFlow]
    npv: Decimal
    total_cost_pv: Decimal
    total_benefit_pv: Decimal
    # Undiscounted, for the "what does it cost in cash" question that always
    # follows the NPV.
    total_cost_nominal: Decimal
    total_benefit_nominal: Decimal
    payback_years: Decimal | None

    @property
    def benefit_cost_ratio(self) -> Decimal | None:
        """Present-value benefits per unit of present-value cost.

        None rather than infinity when there are no costs: a model with no
        costs is a modelling error, and returning a number would hide it.
        """
        if self.total_cost_pv == 0:
            return None
        return (self.total_benefit_pv / self.total_cost_pv).quantize(Decimal("0.001"))

    @property
    def is_positive(self) -> bool:
        return self.npv > 0


def _discount_factor(rate: Decimal, year: int) -> Decimal:
    """1 / (1 + r)^year. Year 0 is undiscounted by convention."""
    if year == 0:
        return Decimal(1)
    return Decimal(1) / ((Decimal(1) + rate) ** year)


def discounted_payback(flows: list[YearFlow], rate: Decimal) -> Decimal | None:
    """Years until discounted cumulative net flow first turns non-negative.

    Interpolated within the year it crosses, so a project that pays back a
    third of the way through year three reports 2.33 rather than 3. The
    integer answer is what makes payback look like a step function and hides
    the difference between a project that just cleared and one that cleared
    comfortably.

    Returns None if it never pays back inside the horizon — deliberately not
    the horizon length, which would read as "pays back in year five".
    """
    cumulative = ZERO
    previous = ZERO
    for flow in sorted(flows, key=lambda f: f.year_index):
        discounted = flow.net * _discount_factor(rate, flow.year_index)
        previous = cumulative
        cumulative += discounted
        if cumulative >= 0 and flow.year_index > 0:
            if discounted == 0:
                return Decimal(flow.year_index)
            fraction = (-previous) / discounted
            fraction = max(ZERO, min(Decimal(1), fraction))
            return (Decimal(flow.year_index - 1) + fraction).quantize(Decimal("0.01"))
        if cumulative >= 0 and flow.year_index == 0:
            # Positive from the outset: no investment to recover.
            return ZERO
    return None


def load_model(session: Session, roi_model_id: int) -> RoiModel:
    model = session.scalar(
        select(RoiModel)
        .options(selectinload(RoiModel.lines).selectinload(RoiLine.amount_assumption))
        .where(RoiModel.id == roi_model_id)
    )
    if model is None:
        raise ValueError(f"roi model {roi_model_id} does not exist")
    return model


def compute(
    model: RoiModel,
    scenario: Scenario = "base",
    overrides: dict[int, Decimal] | None = None,
) -> RoiResult:
    """Full financial picture for one model under one scenario."""
    costs: dict[int, Decimal] = {}
    benefits: dict[int, Decimal] = {}

    for year in range(model.horizon_years):
        costs[year] = ZERO
        benefits[year] = ZERO

    for line in model.lines:
        signed = line_amount(line, scenario, overrides)
        bucket = benefits if line.kind == "benefit" else costs
        # A line beyond the declared horizon is kept rather than dropped: the
        # horizon is a reporting window, and silently discarding cash flows
        # would make the totals disagree with the lines the user entered.
        bucket[line.year_index] = bucket.get(line.year_index, ZERO) + abs(signed)

    years = sorted(set(costs) | set(benefits))
    flows = [
        YearFlow(
            year_index=year,
            costs=costs.get(year, ZERO),
            benefits=benefits.get(year, ZERO),
        )
        for year in years
    ]

    rate = model.discount_rate
    npv = ZERO
    cost_pv = ZERO
    benefit_pv = ZERO
    for flow in flows:
        factor = _discount_factor(rate, flow.year_index)
        npv += flow.net * factor
        cost_pv += flow.costs * factor
        benefit_pv += flow.benefits * factor

    return RoiResult(
        scenario=scenario,
        currency=model.currency,
        discount_rate=rate,
        horizon_years=model.horizon_years,
        flows=flows,
        npv=npv.quantize(Decimal("0.01")),
        total_cost_pv=cost_pv.quantize(Decimal("0.01")),
        total_benefit_pv=benefit_pv.quantize(Decimal("0.01")),
        total_cost_nominal=sum((f.costs for f in flows), ZERO).quantize(Decimal("0.01")),
        total_benefit_nominal=sum((f.benefits for f in flows), ZERO).quantize(Decimal("0.01")),
        payback_years=discounted_payback(flows, rate),
    )


def compare_scenarios(model: RoiModel) -> dict[Scenario, RoiResult]:
    return {scenario: compute(model, scenario) for scenario in SCENARIOS}


@dataclass(frozen=True)
class TornadoRow:
    assumption_id: int
    code: str
    label: str
    unit: str | None
    confidence: str
    source: str | None
    base_value: Decimal
    low_value: Decimal
    high_value: Decimal
    npv_at_low: Decimal
    npv_at_high: Decimal

    @property
    def swing(self) -> Decimal:
        """How much NPV moves across the assumption's whole stated range."""
        return abs(self.npv_at_high - self.npv_at_low)

    @property
    def has_range(self) -> bool:
        return self.low_value != self.high_value

    @property
    def flips_the_decision(self) -> bool:
        """True when one end of the range makes the case, and the other breaks it.

        The single most useful flag in the whole module. An assumption that
        moves NPV by a lot but never crosses zero is a precision problem; one
        that crosses zero means the recommendation itself rests on a number
        somebody guessed.
        """
        return (self.npv_at_low > 0) != (self.npv_at_high > 0)


def tornado(model: RoiModel, base_npv: Decimal | None = None) -> list[TornadoRow]:
    """One row per assumption used by the model, ranked by swing.

    Only assumptions actually referenced by a ROI line appear: an assumption
    that sizes a branch of the cause tree but no cash flow cannot move the
    NPV, and listing it at zero swing would bury the ones that can.
    """
    if base_npv is None:
        base_npv = compute(model, "base").npv

    used: dict[int, Assumption] = {}
    for line in model.lines:
        used[line.amount_assumption_id] = line.amount_assumption

    rows: list[TornadoRow] = []
    for assumption_id, assumption in used.items():
        low = assumption.low_value if assumption.low_value is not None else assumption.base_value
        high = assumption.high_value if assumption.high_value is not None else assumption.base_value

        npv_at_low = compute(model, "base", overrides={assumption_id: low}).npv
        npv_at_high = compute(model, "base", overrides={assumption_id: high}).npv

        rows.append(
            TornadoRow(
                assumption_id=assumption_id,
                code=assumption.code,
                label=assumption.label,
                unit=assumption.unit,
                confidence=assumption.confidence,
                source=assumption.source,
                base_value=assumption.base_value,
                low_value=low,
                high_value=high,
                npv_at_low=npv_at_low,
                npv_at_high=npv_at_high,
            )
        )

    rows.sort(key=lambda row: (-row.swing, row.code))
    return rows


@dataclass(frozen=True)
class FragilityReport:
    """What the review board will attack, computed rather than guessed."""

    base_npv: Decimal
    pessimistic_npv: Decimal
    optimistic_npv: Decimal
    decision_flipping: list[TornadoRow] = field(default_factory=list)
    unsourced: list[TornadoRow] = field(default_factory=list)
    low_confidence_high_impact: list[TornadoRow] = field(default_factory=list)
    point_estimates: list[TornadoRow] = field(default_factory=list)

    @property
    def survives_pessimistic(self) -> bool:
        return self.pessimistic_npv > 0

    @property
    def only_fails_in_combination(self) -> bool:
        """No single assumption breaks the case, but all of them together do.

        Worth separating from `decision_flipping` because the two demand
        different answers. A single flipping assumption is a research task:
        go and measure that one number. A case that survives every individual
        assumption but fails when they all land badly is a *correlation*
        question — are these risks independent, or do they arrive together?
        In this domain they usually arrive together, which is why a model
        that passes the tornado can still be the wrong call.
        """
        return not self.decision_flipping and self.base_npv > 0 >= self.pessimistic_npv

    @property
    def headline(self) -> str:
        if self.base_npv <= 0:
            return "The base case does not pay for itself."
        if self.only_fails_in_combination:
            return (
                "No single assumption breaks the case, but the pessimistic "
                "scenario does. The question is whether these risks are "
                "independent — if they arrive together, the base case is optimistic."
            )
        if self.decision_flipping:
            codes = ", ".join(row.code for row in self.decision_flipping)
            return (
                f"The recommendation depends on {codes}: within the stated "
                "range, the sign of the NPV changes."
            )
        return "The case holds across every stated range, including the pessimistic scenario."


def fragility(model: RoiModel, top_n: int = 3) -> FragilityReport:
    """The assumptions worth defending, in the order they will be attacked.

    Four findings, in descending order of how much trouble they cause:

      - an assumption whose range flips the sign of the NPV;
      - an assumption carrying real weight with no source;
      - a low-confidence assumption among the largest swings;
      - a point estimate — no range at all — which cannot be tested here and
        so is invisible to the tornado.
    """
    base = compute(model, "base")
    rows = tornado(model, base.npv)
    ranked = [row for row in rows if row.has_range]

    return FragilityReport(
        base_npv=base.npv,
        pessimistic_npv=compute(model, "pessimistic").npv,
        optimistic_npv=compute(model, "optimistic").npv,
        decision_flipping=[row for row in ranked if row.flips_the_decision],
        unsourced=[row for row in ranked if not row.source],
        low_confidence_high_impact=[
            row for row in ranked[:top_n] if row.confidence == "low"
        ],
        point_estimates=[row for row in rows if not row.has_range],
    )
