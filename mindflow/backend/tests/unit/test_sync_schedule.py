"""When the scheduler decides a connection is due.

`is_due` is pure, and it is the whole scheduling policy: everything else in the
job is plumbing. The cases that matter are the ones where being wrong is not
merely inefficient —

* retrying an `expired`-bound connection forever burns provider quota and buries
  the only fix, which is asking the user to reconnect;
* retrying a *failing* one every tick is how an integration earns a rate-limit
  ban;
* not retrying a healthy one is a synchronisation that silently stopped.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.sync import MAX_CONSECUTIVE_FAILURES, Provider, backoff_seconds
from app.workers.scheduled.synchroniser import SERVER_SIDE_PROVIDERS, is_due

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
INTERVAL = 300


def _due(
    *,
    last_sync_at: datetime | None = None,
    updated_at: datetime | None = None,
    failures: int = 0,
) -> bool:
    return is_due(
        last_sync_at=last_sync_at,
        updated_at=updated_at,
        consecutive_failures=failures,
        interval_seconds=INTERVAL,
        now=NOW,
    )


class TestHealthyConnections:
    def test_a_connection_that_never_synced_is_due_immediately(self) -> None:
        # The first pass after connecting. Waiting five minutes to show anything
        # reads as a connection that did not work.
        assert _due(last_sync_at=None) is True

    def test_a_connection_synced_within_the_interval_is_not_due(self) -> None:
        assert _due(last_sync_at=NOW - timedelta(seconds=INTERVAL - 1)) is False

    def test_a_connection_synced_exactly_one_interval_ago_is_due(self) -> None:
        assert _due(last_sync_at=NOW - timedelta(seconds=INTERVAL)) is True

    def test_a_stale_connection_is_due(self) -> None:
        assert _due(last_sync_at=NOW - timedelta(hours=3)) is True


class TestFailingConnections:
    def test_a_failing_connection_is_not_retried_on_the_next_tick(self) -> None:
        # One failure buys a minute. Retrying immediately is how a provider
        # having a bad minute becomes a provider that rate-limits us.
        assert _due(updated_at=NOW - timedelta(seconds=30), failures=1) is False

    def test_it_is_retried_once_its_backoff_has_elapsed(self) -> None:
        delay = backoff_seconds(1)
        assert _due(updated_at=NOW - timedelta(seconds=delay), failures=1) is True

    @pytest.mark.parametrize("failures", [1, 2, 3, 4, 5])
    def test_the_backoff_grows_with_each_failure(self, failures: int) -> None:
        # Just short of the current backoff: not due. This is the property that
        # makes a long outage cheap instead of expensive.
        just_under = backoff_seconds(failures) - 1
        assert _due(updated_at=NOW - timedelta(seconds=just_under), failures=failures) is False
        assert (
            _due(updated_at=NOW - timedelta(seconds=backoff_seconds(failures)), failures=failures)
            is True
        )

    def test_the_backoff_is_capped_at_an_hour(self) -> None:
        # A provider having a bad *day* must not be abandoned within it.
        assert backoff_seconds(20) == 3600
        assert _due(updated_at=NOW - timedelta(hours=1), failures=5) is True

    def test_the_scheduler_gives_up_after_the_failure_ceiling(self) -> None:
        # Six failures over a five-minute cadence is half an hour of a token
        # that is almost certainly revoked. Only reconnecting clears it, and
        # reconnecting resets the counter.
        assert _due(updated_at=NOW - timedelta(days=7), failures=MAX_CONSECUTIVE_FAILURES) is False
        assert _due(updated_at=NOW - timedelta(days=7), failures=99) is False

    def test_a_failing_connection_with_no_timestamps_is_retried_once(self) -> None:
        # Nothing to compute a backoff from. Attempting is the safe direction:
        # the attempt itself writes the timestamp the next tick will use.
        assert _due(failures=2) is True

    def test_it_falls_back_to_last_sync_at_when_updated_at_is_missing(self) -> None:
        assert _due(last_sync_at=NOW - timedelta(seconds=10), failures=1) is False
        assert _due(last_sync_at=NOW - timedelta(hours=2), failures=1) is True


class TestTheProviderFilter:
    def test_obsidian_is_never_scheduled(self) -> None:
        # It is a folder on somebody's disk. Scheduling it would produce a pass
        # that exists only to refuse itself.
        assert Provider.OBSIDIAN.value not in SERVER_SIDE_PROVIDERS

    def test_every_other_provider_is(self) -> None:
        for provider in Provider:
            if provider is Provider.OBSIDIAN:
                continue
            assert provider.value in SERVER_SIDE_PROVIDERS

    def test_the_filter_is_derived_from_the_provider_not_listed_by_hand(self) -> None:
        # A new connector must not have to remember to add itself here.
        assert set(SERVER_SIDE_PROVIDERS) == {
            provider.value for provider in Provider if provider.is_server_side
        }
