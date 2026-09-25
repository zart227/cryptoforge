from __future__ import annotations

import gzip
import shutil
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class DiskStatus(StrEnum):
    NORMAL = "normal"
    WARNING = "warning"
    CLEANUP = "cleanup"
    CRITICAL = "critical"


class DataClass(StrEnum):
    CRITICAL = "critical"
    REPRODUCIBLE = "reproducible"
    TEMPORARY = "temporary"


@dataclass(frozen=True)
class DiskThresholds:
    warning_percent: float = 70.0
    cleanup_percent: float = 80.0
    critical_percent: float = 90.0


@dataclass(frozen=True)
class CleanupTarget:
    path: Path
    data_class: DataClass


@dataclass(frozen=True)
class CleanupResult:
    removed_paths: tuple[Path, ...]
    skipped_critical_paths: tuple[Path, ...]
    freed_bytes: int


@dataclass(frozen=True)
class DiskDecision:
    status: DiskStatus
    usage_percent: float
    message: str
    allow_research: bool
    should_cleanup_safe_data: bool
    should_emit_critical: bool


def classify_disk_usage(
    usage_percent: float,
    thresholds: DiskThresholds | None = None,
) -> DiskDecision:
    limits = thresholds or DiskThresholds()
    if usage_percent >= limits.critical_percent:
        return DiskDecision(
            status=DiskStatus.CRITICAL,
            usage_percent=usage_percent,
            message="disk usage is critical; stop research and emit critical warning",
            allow_research=False,
            should_cleanup_safe_data=True,
            should_emit_critical=True,
        )
    if usage_percent >= limits.cleanup_percent:
        return DiskDecision(
            status=DiskStatus.CLEANUP,
            usage_percent=usage_percent,
            message="disk usage requires cleanup of safe temporary/reproducible data",
            allow_research=False,
            should_cleanup_safe_data=True,
            should_emit_critical=False,
        )
    if usage_percent >= limits.warning_percent:
        return DiskDecision(
            status=DiskStatus.WARNING,
            usage_percent=usage_percent,
            message="disk usage warning",
            allow_research=True,
            should_cleanup_safe_data=False,
            should_emit_critical=False,
        )
    return DiskDecision(
        status=DiskStatus.NORMAL,
        usage_percent=usage_percent,
        message="disk usage normal",
        allow_research=True,
        should_cleanup_safe_data=False,
        should_emit_critical=False,
    )


def cleanup_safe_targets(targets: list[CleanupTarget] | tuple[CleanupTarget, ...]) -> CleanupResult:
    removed: list[Path] = []
    skipped_critical: list[Path] = []
    freed_bytes = 0

    for target in targets:
        if target.data_class == DataClass.CRITICAL:
            skipped_critical.append(target.path)
            continue

        path = target.path
        if not path.exists():
            continue

        freed_bytes += path_size(path)
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        removed.append(path)

    return CleanupResult(
        removed_paths=tuple(removed),
        skipped_critical_paths=tuple(skipped_critical),
        freed_bytes=freed_bytes,
    )


def path_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            total += child.stat().st_size
    return total


def rotate_log_file(
    path: Path,
    *,
    max_bytes: int,
    keep: int,
    compress: bool = True,
) -> bool:
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    if keep < 1:
        raise ValueError("keep must be at least 1")
    if not path.exists() or path.stat().st_size < max_bytes:
        return False

    suffix = ".gz" if compress else ""
    oldest = path.with_name(f"{path.name}.{keep}{suffix}")
    if oldest.exists():
        oldest.unlink()

    for index in range(keep - 1, 0, -1):
        current = path.with_name(f"{path.name}.{index}{suffix}")
        next_path = path.with_name(f"{path.name}.{index + 1}{suffix}")
        if current.exists():
            current.rename(next_path)

    first_rotated = path.with_name(f"{path.name}.1{suffix}")
    if compress:
        with path.open("rb") as source, gzip.open(first_rotated, "wb") as destination:
            shutil.copyfileobj(source, destination)
        path.unlink()
    else:
        path.rename(first_rotated)

    path.touch()
    return True
