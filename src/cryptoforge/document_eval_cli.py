from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from cryptoforge.document_eval import (
    DEFAULT_EXTENSIONS,
    DEFAULT_RUBRIC_PATH,
    discover_documents,
    evaluate_documents,
    load_rubric,
    results_to_json,
    table,
    write_csv,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate documents across rubric dimensions with the TypeSafe System One API."
    )
    parser.add_argument("paths", nargs="+", type=Path, help="Document files or directories to evaluate.")
    parser.add_argument(
        "--rubric",
        type=Path,
        default=DEFAULT_RUBRIC_PATH,
        help="JSON rubric file defining TypeSafe Score dimensions.",
    )
    parser.add_argument("--model", help="Override the TypeSafe model, e.g. jev-latest.")
    parser.add_argument(
        "--extensions",
        default=",".join(DEFAULT_EXTENSIONS),
        help="Comma-separated extensions to include when scanning directories.",
    )
    parser.add_argument("--json-out", type=Path, help="Write full JSON results to this file.")
    parser.add_argument("--csv-out", type=Path, help="Write flat CSV results to this file.")
    parser.add_argument(
        "--format",
        choices=("table", "json"),
        default="table",
        help="Format printed to stdout.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on the first TypeSafe API error instead of recording an error row.",
    )
    args = parser.parse_args(argv)

    rubric = load_rubric(args.rubric)
    extensions = tuple(item.strip().lower() for item in args.extensions.split(",") if item.strip())
    documents = discover_documents(args.paths, extensions=extensions)
    if not documents:
        print("No non-empty documents found.", file=sys.stderr)
        return 1
    if not os.environ.get("TYPESAFE_API_KEY"):
        print("TYPESAFE_API_KEY is required to call the TypeSafe API.", file=sys.stderr)
        return 2

    results = evaluate_documents(
        documents,
        rubric,
        model=args.model,
        continue_on_error=not args.fail_fast,
    )

    if args.json_out:
        args.json_out.write_text(results_to_json(results) + "\n", encoding="utf-8")
    if args.csv_out:
        write_csv(results, args.csv_out)

    if args.format == "json":
        print(results_to_json(results))
    else:
        print(table(results))

    return 1 if any(result.error for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
