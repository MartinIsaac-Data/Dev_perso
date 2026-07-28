"""Cause tree computation and reconciliation against the claimed loss.

The tree is quantified strictly bottom-up. A leaf is the product of its
drivers — `120 pallets/week × 52 weeks × 38 EUR of rework` is three
assumptions multiplied, not one number typed in — and an internal node is the
sum of its children. No node stores its own value.

The most useful output here is the one nobody wants: the gap between what the
tree adds up to and what the client claimed. In the demonstration case that
gap is 707,392 EUR, or 16.8%, and it is the first thing the review board
attacks. A tool that quietly reconciled the difference — by scaling the tree,
or by adding an "other" branch — would be removing the single most instructive
number in the exercise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Assumption, BusinessCase, CauseDriver, CauseNode
from app.services.roi import ZERO, Scenario, assumption_value


@dataclass(frozen=True)
class DriverBreakdown:
    assumption_id: int
    code: str
    label: str
    unit: str | None
    value: Decimal
    confidence: str
    has_source: bool


@dataclass
class CauseNodeValue:
    node_id: int
    parent_id: int | None
    label: str
    description: str | None
    evidence_note: str | None
    depth: int
    is_leaf: bool
    value: Decimal
    drivers: list[DriverBreakdown] = field(default_factory=list)
    children: list[CauseNodeValue] = field(default_factory=list)

    @property
    def share_of_parent(self) -> Decimal | None:
        return None  # filled in by the caller, which knows the parent total


@dataclass(frozen=True)
class Reconciliation:
    """Bottom-up total against the figure the client asserted."""

    bottom_up_total: Decimal
    claimed_annual_loss: Decimal | None
    currency: str

    @property
    def gap(self) -> Decimal | None:
        if self.claimed_annual_loss is None:
            return None
        return self.claimed_annual_loss - self.bottom_up_total

    @property
    def gap_ratio(self) -> Decimal | None:
        """Unexplained share of the claimed figure, as a fraction."""
        if self.claimed_annual_loss is None or self.claimed_annual_loss == 0:
            return None
        gap = self.gap
        assert gap is not None
        return (gap / self.claimed_annual_loss).quantize(Decimal("0.0001"))

    @property
    def verdict(self) -> str:
        """A sentence the author has to answer, not a status colour."""
        if self.claimed_annual_loss is None:
            return "No figure was claimed, so there is nothing to reconcile against."
        gap = self.gap
        ratio = self.gap_ratio
        assert gap is not None and ratio is not None
        if abs(ratio) < Decimal("0.05"):
            return "The tree accounts for the claimed figure within 5%."
        if gap > 0:
            return (
                f"The tree explains {self.bottom_up_total:,.0f} of a claimed "
                f"{self.claimed_annual_loss:,.0f}. {gap:,.0f} ({ratio:.1%}) is "
                "unaccounted for: either causes are missing, or the claimed "
                "figure is wrong and should be challenged."
            )
        return (
            f"The tree adds up to {self.bottom_up_total:,.0f} against a claimed "
            f"{self.claimed_annual_loss:,.0f}. The bottom-up total exceeds the "
            "claim by "
            f"{abs(gap):,.0f} ({abs(ratio):.1%}), which usually means a branch "
            "is double-counting."
        )


@dataclass(frozen=True)
class CauseTree:
    scenario: Scenario
    currency: str
    roots: list[CauseNodeValue]
    total: Decimal
    reconciliation: Reconciliation
    # Leaves ranked by value: where the money actually is.
    ranked_leaves: list[CauseNodeValue] = field(default_factory=list)


def leaf_value(drivers: list[CauseDriver], scenario: Scenario) -> Decimal:
    """Product of the leaf's drivers.

    A cause tree measures losses, so it is unfavourable when high: the
    pessimistic scenario takes the top of each assumption's range. An empty
    driver list is zero, not one — a leaf nobody has quantified contributes
    nothing rather than silently contributing a unit.
    """
    if not drivers:
        return ZERO
    value = Decimal(1)
    for driver in sorted(drivers, key=lambda d: d.ordinal):
        value *= assumption_value(
            driver.assumption, scenario, favourable_when_high=False
        )
    return value


def build_cause_tree(
    session: Session, case: BusinessCase, scenario: Scenario = "base"
) -> CauseTree:
    nodes = list(
        session.scalars(
            select(CauseNode)
            .options(
                selectinload(CauseNode.drivers).selectinload(CauseDriver.assumption)
            )
            .where(CauseNode.case_id == case.id)
            .order_by(CauseNode.ordinal, CauseNode.id)
        )
    )

    children_of: dict[int | None, list[CauseNode]] = {}
    for node in nodes:
        children_of.setdefault(node.parent_id, []).append(node)

    leaves: list[CauseNodeValue] = []

    def visit(node: CauseNode, depth: int) -> CauseNodeValue:
        kids = children_of.get(node.id, [])
        computed_children = [visit(child, depth + 1) for child in kids]
        is_leaf = not kids

        if is_leaf:
            value = leaf_value(list(node.drivers), scenario)
        else:
            # An internal node's value is its children's, always. A node with
            # both children and drivers would be double counting, so the
            # drivers are ignored rather than added.
            value = sum((child.value for child in computed_children), ZERO)

        result = CauseNodeValue(
            node_id=node.id,
            parent_id=node.parent_id,
            label=node.label,
            description=node.description,
            evidence_note=node.evidence_note,
            depth=depth,
            is_leaf=is_leaf,
            value=value,
            drivers=[
                DriverBreakdown(
                    assumption_id=driver.assumption_id,
                    code=driver.assumption.code,
                    label=driver.assumption.label,
                    unit=driver.assumption.unit,
                    value=assumption_value(
                        driver.assumption, scenario, favourable_when_high=False
                    ),
                    confidence=driver.assumption.confidence,
                    has_source=bool(driver.assumption.source),
                )
                for driver in sorted(node.drivers, key=lambda d: d.ordinal)
            ],
            children=computed_children,
        )
        if is_leaf:
            leaves.append(result)
        return result

    roots = [visit(node, 0) for node in children_of.get(None, [])]
    total = sum((root.value for root in roots), ZERO)

    return CauseTree(
        scenario=scenario,
        currency=case.currency,
        roots=roots,
        total=total,
        reconciliation=Reconciliation(
            bottom_up_total=total,
            claimed_annual_loss=case.claimed_annual_loss,
            currency=case.currency,
        ),
        ranked_leaves=sorted(leaves, key=lambda leaf: -leaf.value),
    )


@dataclass(frozen=True)
class AssumptionAudit:
    """Where a case is weakest, before anyone else points it out."""

    total: int
    unsourced: list[str]
    point_estimates: list[str]
    low_confidence: list[str]
    unused: list[str]

    @property
    def sourced_ratio(self) -> Decimal:
        if self.total == 0:
            return ZERO
        return Decimal(self.total - len(self.unsourced)) / Decimal(self.total)


def audit_assumptions(session: Session, case: BusinessCase) -> AssumptionAudit:
    """Structural checks that need no financial model to run.

    `unused` matters more than it looks: an assumption nobody references is
    either a leftover from a discarded branch, or a number the author meant to
    use and forgot — and the second case means the model is missing a cost.
    """
    assumptions = list(
        session.scalars(select(Assumption).where(Assumption.case_id == case.id))
    )

    referenced: set[int] = set()
    for driver in session.scalars(
        select(CauseDriver).join(CauseNode).where(CauseNode.case_id == case.id)
    ):
        referenced.add(driver.assumption_id)
    for model in case.roi_models:
        for line in model.lines:
            referenced.add(line.amount_assumption_id)

    return AssumptionAudit(
        total=len(assumptions),
        unsourced=sorted(a.code for a in assumptions if not a.source),
        point_estimates=sorted(
            a.code
            for a in assumptions
            if a.low_value is None
            or a.high_value is None
            or a.low_value == a.high_value
        ),
        low_confidence=sorted(a.code for a in assumptions if a.confidence == "low"),
        unused=sorted(a.code for a in assumptions if a.id not in referenced),
    )
