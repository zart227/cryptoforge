from __future__ import annotations

import argparse

from cryptoforge.model_registry import ActiveModelRegistry
from cryptoforge.supabase_market import SupabaseRestClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect the active CryptoForge model published in Supabase.")
    parser.add_argument("--supabase-timeout", type=float, default=15.0)
    args = parser.parse_args()

    model = ActiveModelRegistry(
        SupabaseRestClient.from_env(timeout_seconds=args.supabase_timeout)
    ).latest()
    if model is None:
        print("active_model=none")
        return 1
    metrics = model.artifact.get("metrics", [])
    print(
        "active_model version={version} run={run} occurred_at={occurred_at} sha256={sha256} metrics={metrics}".format(
            version=model.model_version,
            run=model.model_run_id,
            occurred_at=model.occurred_at.isoformat(),
            sha256=model.artifact_sha256[:12],
            metrics=metrics,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
