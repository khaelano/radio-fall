"""Conservative grant-timing model; produces no synthetic CSI or RF evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math


@dataclass(frozen=True)
class TimingGrant:
    """One simulated authorization and its assumed return confirmation."""

    grant_id: int
    owner: int
    announced_ms: float
    start_ms: float
    end_ms: float
    confirmed_ms: float | None


@dataclass(frozen=True)
class TimingPhase:
    """One modeled phase, not an observed channel transition."""

    owner: int
    start_ms: float
    end_ms: float
    state: str


@dataclass(frozen=True)
class TimingSimulation:
    """Model output with explicit assumptions and conservative availability."""

    slot_ms: int
    receiver_count: int
    horizon_ms: float
    nominal_revisit_ms: float
    grants: tuple[TimingGrant, ...]
    phases: tuple[TimingPhase, ...]
    maximum_off_channel_or_unconfirmed: int
    minimum_potential_sensing_receivers: int

    def as_dict(self) -> dict:
        """Return serializable timings without simulated measurements."""
        return asdict(self)


def simulate_receiver_timing(
    slot_ms: int,
    *,
    receiver_count: int = 4,
    cycles: int = 2,
    sensing_hz: int = 80,
    lost_return_grant: int | None = None,
) -> TimingSimulation:
    """Simulate fixed-roster grants and stop departures after a lost return.

    This planning model assumes readiness, a two-round announcement lead, and
    confirmation processed on the first sensing tick at/after each slot end.
    It assumes a 5 ms departure guard, 5 ms outward switch and a 10 ms return
    reserve. The colored upload phase denotes authorization, not continuous
    transmission. Actual firmware may return earlier, skip grants, or recover
    later; it aligns its send cutoff to sensing witnesses. RF/MAC contention,
    clock uncertainty, power behavior and CSI are intentionally not simulated.

    Args:
        slot_ms: Authorized window, between 25 and 500 ms.
        receiver_count: Number of fixed receiver identities, from one to four.
        cycles: Number of complete round-robin cycles in the normal scenario.
        sensing_hz: Sensing reference rate, between 50 and 120 Hz.
        lost_return_grant: Optional one-based grant whose confirmation is lost.

    Returns:
        Nominal grants/phases and potential capture coverage under assumptions.
    """
    if type(slot_ms) is not int or not 25 <= slot_ms <= 500:
        raise ValueError("invalid slot duration")
    if not 1 <= receiver_count <= 4 or not 1 <= cycles <= 100:
        raise ValueError("invalid receiver/cycle count")
    if not 50 <= sensing_hz <= 120:
        raise ValueError("invalid sensing rate")
    count = receiver_count * cycles
    if lost_return_grant is not None and not 1 <= lost_return_grant <= count:
        raise ValueError("lost return is outside the simulated grants")
    period = 1000 / sensing_hz
    lead = 2 * period
    grants = []
    now = 0.0
    for i in range(count):
        start = now + lead
        end = start + slot_ms
        confirmed = math.ceil((end - 1e-9) / period) * period
        grants.append(
            TimingGrant(i + 1, i % receiver_count, now, start, end, confirmed)
        )
        now = confirmed
    horizon = now + lead
    revisit = (
        grants[receiver_count].start_ms - grants[0].start_ms
        if cycles > 1
        else (math.ceil(slot_ms / period) * period + lead) * receiver_count
    )
    if lost_return_grant is not None:
        grants = grants[:lost_return_grant]
        last = grants[-1]
        grants[-1] = TimingGrant(
            last.grant_id,
            last.owner,
            last.announced_ms,
            last.start_ms,
            last.end_ms,
            None,
        )
    phases = []
    for grant in grants:
        departure = grant.start_ms + 5
        phases.extend(
            (
                TimingPhase(grant.owner, departure, departure + 5, "switch_to_2g"),
                TimingPhase(grant.owner, departure + 5, grant.end_ms - 10, "upload"),
                TimingPhase(
                    grant.owner, grant.end_ms - 10, grant.end_ms - 5, "return_to_5g"
                ),
                TimingPhase(
                    grant.owner,
                    grant.end_ms - 5,
                    grant.confirmed_ms if grant.confirmed_ms is not None else horizon,
                    "confirm_return"
                    if grant.confirmed_ms is not None
                    else "unconfirmed",
                ),
            )
        )
    points = sorted(
        {0.0, horizon, *(p.start_ms for p in phases), *(p.end_ms for p in phases)}
    )
    maximum = 0
    for left, right in zip(points, points[1:]):
        middle = (left + right) / 2
        owners = {p.owner for p in phases if p.start_ms <= middle < p.end_ms}
        maximum = max(maximum, len(owners))
    return TimingSimulation(
        slot_ms,
        receiver_count,
        horizon,
        revisit,
        tuple(grants),
        tuple(phases),
        maximum,
        receiver_count - maximum,
    )
