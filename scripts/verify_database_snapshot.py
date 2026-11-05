"""Compare every restored app row with the source snapshot's sorted digests."""
import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from database_backend import STATE
from import_database_snapshot import ident, literal


def verify(directory: Path, *, database: str = "cryptoforge") -> dict:
    expected = json.loads((directory / "source-hashes.json").read_text())
    statements = []
    for table in expected:
        schema, name = table["table_name"].split(".", 1)
        qualified = ident(schema) + "." + ident(name)
        statements.append(f"SELECT {literal(table['table_name'])} as table_name, count(*) as rows, "
                          "md5(coalesce(string_agg(md5(row_to_json(t)::text),'' order by id),'')) "
                          f"as content_hash FROM {qualified} t")
    query = "SET TIME ZONE 'UTC'; SELECT json_agg(t) FROM (" + " UNION ALL ".join(statements) + ") t;"
    command = ["docker", "compose", "--env-file", str(STATE / "compose.env"), "-f",
               str(ROOT / "docker/database.compose.yml"), "exec", "-T", "db", "psql",
               "-X", "-qAt", "-U", "postgres", "-d", database, "-v", "ON_ERROR_STOP=1"]
    result = subprocess.run(command, input=query, text=True, capture_output=True, check=True)
    actual = sorted(json.loads(result.stdout), key=lambda table: table["table_name"])
    expected.sort(key=lambda table: table["table_name"])
    matched = actual == expected
    report = {"verified_at": datetime.now(UTC).isoformat(), "database": database, "all_tables_match": matched,
              "table_count": len(actual), "total_rows": sum(t["rows"] for t in actual), "tables": actual}
    report_name = "verification.json" if database == "cryptoforge" else "backup-restore-verification.json"
    (directory / report_name).write_text(json.dumps(report, indent=2) + "\n")
    if not matched:
        raise ValueError("Source/local content mismatch; do not switch backends")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    report = verify(parser.parse_args().directory)
    print(f"Verified {report['table_count']} tables, {report['total_rows']} rows: all content hashes match")
