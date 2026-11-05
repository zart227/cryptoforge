"""Exact, preregistered lifecycle and time coverage for isolated paper capture."""
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
import os


def utc(value):
    result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('aware lifecycle clock required')
    return result.astimezone(UTC)


def seconds(delta):
    return Decimal(delta.days*86400+delta.seconds)+Decimal(delta.microseconds)/1000000


@dataclass(frozen=True)
class PaperLifecycle:
    poll_seconds: int
    maximum_operations_per_poll: int
    estimated_bytes_per_operation: int
    maximum_mark_gap_seconds: int
    maximum_endpoint_gap_seconds: int
    minimum_known_time_fraction: str
    closeout_seconds: int
    finalization_grace_seconds: int
    maximum_operation_wall_seconds: int
    maximum_storage_bytes: int
    minimum_free_disk_bytes: int
    minimum_available_memory_bytes: int

    def __post_init__(self):
        for key, value in asdict(self).items():
            if key != 'minimum_known_time_fraction' and (type(value) is not int or value < 1):
                raise ValueError('explicit positive integer lifecycle limits required')
        fraction = Decimal(str(self.minimum_known_time_fraction))
        if not fraction.is_finite() or not 0 < fraction <= 1:
            raise ValueError('explicit positive known-time fraction required')
        object.__setattr__(self, 'minimum_known_time_fraction', str(fraction))
        if (self.poll_seconds > self.maximum_mark_gap_seconds
                or self.maximum_operation_wall_seconds > self.poll_seconds
                or not 65536 <= self.maximum_storage_bytes <= 64*1024*1024
                or self.minimum_free_disk_bytes < self.maximum_storage_bytes
                or self.estimated_bytes_per_operation > 512*1024):
            raise ValueError('inconsistent lifecycle resource/cadence limits')

    def payload(self):
        return dict(schema_version='paper-lifecycle-v1', **asdict(self))

    @classmethod
    def from_payload(cls, payload):
        payload = dict(payload)
        if payload.pop('schema_version', None) != 'paper-lifecycle-v1':
            raise ValueError('known lifecycle schema required')
        return cls(**payload)

    def capacity_requirements(self, start, end):
        duration = seconds(utc(end)-utc(start))
        if duration <= self.closeout_seconds:
            raise ValueError('closeout must fit within a positive prospective window')
        slots = int((duration/self.poll_seconds).to_integral_value(rounding=ROUND_CEILING))
        operations = slots*self.maximum_operations_per_poll+1  # one final endpoint mark
        required_events = 1+2*operations+1  # genesis, prepared/completed pairs, terminal
        estimated_bytes = 65536+operations*self.estimated_bytes_per_operation
        return dict(poll_slots=slots, maximum_operations=operations, required_events=required_events,
                    estimated_storage_bytes=estimated_bytes,
                    entry_cutoff=(utc(end)-timedelta(seconds=self.closeout_seconds)).isoformat(),
                    estimate_is_host_qualification=False)

    def plan(self, start, end, *, max_events):
        if type(max_events) is not int or max_events < 1:
            raise ValueError('explicit positive event budget required')
        requirements = self.capacity_requirements(start, end)
        required_events = requirements['required_events']
        if required_events > max_events:
            raise ValueError(f'lifecycle needs {required_events} events; budget is {max_events}')
        if requirements['estimated_storage_bytes'] > self.maximum_storage_bytes:
            raise ValueError('estimated lifecycle storage exceeds frozen budget')
        return requirements


def measure_resources(root):
    parent = Path(root).absolute()
    while not parent.exists():
        parent = parent.parent
    stats = os.statvfs(parent)
    available = None
    try:
        for line in Path('/proc/meminfo').read_text().splitlines():
            if line.startswith('MemAvailable:'):
                available = int(line.split()[1])*1024
                break
    except (OSError, ValueError, IndexError):
        pass
    storage = sum(path.stat().st_size for path in Path(root).iterdir() if path.is_file()) if Path(root).is_dir() else 0
    return dict(available_memory_bytes=available, free_disk_bytes=stats.f_bavail*stats.f_frsize,
                storage_bytes=storage)


def resource_blocker(policy, measured, *, reserve_bytes=0):
    for key in ('available_memory_bytes', 'free_disk_bytes', 'storage_bytes'):
        if type(measured.get(key)) is not int or measured[key] < 0:
            return 'resource_measurement_unknown'
    if measured['available_memory_bytes'] < policy.minimum_available_memory_bytes:
        return 'available_memory_below_frozen_minimum'
    if measured['free_disk_bytes'] < policy.minimum_free_disk_bytes+reserve_bytes:
        return 'free_disk_below_frozen_minimum'
    if measured['storage_bytes']+reserve_bytes > policy.maximum_storage_bytes:
        return 'capture_storage_budget_exhausted'
    return None


def mark_valid_until(policy, at, before, quotes, filters, config):
    at = utc(at)
    deadline = at+timedelta(seconds=policy.maximum_mark_gap_seconds)
    pairs = {lot['pair'] for lot in before['lots'] if Decimal(lot['qty']) > 0}
    for pair in pairs:
        if pair not in quotes or pair not in filters:
            return at
        deadline = min(deadline,
            utc(quotes[pair]['observed_at'])+timedelta(seconds=config.quote_max_age_seconds),
            utc(filters[pair]['observed_at'])+timedelta(seconds=config.filter_max_age_seconds))
    return max(at, deadline)


class CoverageTimeline:
    """Integrate known time; duplicates cannot increase coverage.

    Every prepared operation invalidates the previous observation. A mark is
    available only on completion and only until its ORIGINAL sources expire.
    """
    def __init__(self, start, end, policy):
        self.start, self.end, self.policy = utc(start), utc(end), policy
        self.cursor, self.until = self.start, self.start
        self.intervals, self.mark_clocks = [], []

    def _advance(self, at):
        at = min(utc(at), self.end)
        if at < self.cursor:
            raise ValueError('coverage events must be causal')
        finish = min(at, self.until)
        if finish > self.cursor:
            if self.intervals and self.intervals[-1][1] == self.cursor:
                self.intervals[-1] = (self.intervals[-1][0], finish)
            else:
                self.intervals.append((self.cursor, finish))
        self.cursor = at

    def invalidate(self, at):
        self._advance(at)
        self.until = self.cursor

    def mark(self, at, valid_until, *, sources_known):
        at = utc(at)
        self._advance(at)
        self.mark_clocks.append(at)
        self.until = min(utc(valid_until), self.end) if sources_known else self.cursor

    def finish(self):
        self._advance(self.end)
        total = seconds(self.end-self.start)
        known = sum((seconds(b-a) for a, b in self.intervals), Decimal(0))
        unknown = []
        cursor = self.start
        for left, right in self.intervals:
            unknown.append(seconds(left-cursor))
            cursor = right
        unknown.append(seconds(self.end-cursor))
        clocks = [self.start, *self.mark_clocks, self.end]
        maximum_mark_gap = max(seconds(b-a) for a, b in zip(clocks, clocks[1:]))
        leading = seconds(self.intervals[0][0]-self.start) if self.intervals else total
        trailing = seconds(self.end-self.intervals[-1][1]) if self.intervals else total
        fraction = known/total
        checks = dict(
            known_time_fraction=fraction >= Decimal(self.policy.minimum_known_time_fraction),
            mark_cadence=maximum_mark_gap <= self.policy.maximum_mark_gap_seconds,
            unknown_gap=max(unknown) <= self.policy.maximum_mark_gap_seconds,
            leading_endpoint=leading <= self.policy.maximum_endpoint_gap_seconds,
            trailing_endpoint=trailing <= self.policy.maximum_endpoint_gap_seconds)
        return dict(window_seconds=str(total), known_seconds=str(known), known_fraction=str(fraction),
                    maximum_mark_gap_seconds=str(maximum_mark_gap), maximum_unknown_gap_seconds=str(max(unknown)),
                    leading_unknown_seconds=str(leading), trailing_unknown_seconds=str(trailing),
                    checks=checks, coverage_pass=all(checks.values()),
                    covers_end=bool(self.intervals) and self.intervals[-1][1] == self.end)
