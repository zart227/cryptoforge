"""Restore a reviewed catalog + raw JSON snapshot into an EMPTY local backend.

Used when Supabase's Data API is quota-blocked and only Management SQL is
available. Never parses/re-encodes numeric row values through Python floats.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from database_backend import STATE


def ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def table_name(table: dict) -> str:
    return ident(table["schema"]) + "." + ident(table["name"])


def schema_statements(metadata: dict):
    # The snapshot stores app schemas only, not Supabase platform internals.
    for schema in ("internal", "freqtrade"):
        yield f"CREATE SCHEMA {ident(schema)};"
    yield "REVOKE ALL ON SCHEMA freqtrade, internal FROM PUBLIC;"
    yield "CREATE EXTENSION pgcrypto WITH SCHEMA internal;"
    for enum in metadata.get("enums") or []:
        labels = ",".join(literal(label) for label in enum["labels"])
        yield f"CREATE TYPE {table_name(enum)} AS ENUM ({labels});"
    for sequence in metadata.get("sequences") or []:
        name = ident(sequence["schemaname"]) + "." + ident(sequence["sequencename"])
        yield (f"CREATE SEQUENCE {name} AS {sequence['data_type']} "
               f"INCREMENT {sequence['increment_by']} MINVALUE {sequence['min_value']} "
               f"MAXVALUE {sequence['max_value']} START {sequence['start_value']} "
               f"CACHE {sequence['cache_size']} " + ("CYCLE;" if sequence['cycle'] else "NO CYCLE;"))
    for function in metadata.get("functions") or []:
        yield function.rstrip().rstrip(";") + ";"
    yield "REVOKE ALL ON ALL FUNCTIONS IN SCHEMA internal FROM PUBLIC;"
    for table in metadata["tables"]:
        columns = []
        for column in table["columns"]:
            if column["identity"] or column["generated"]:
                raise ValueError("Identity/generated columns require a pg_dump restore")
            definition = ident(column["name"]) + " " + column["type"]
            if column["default"] is not None:
                definition += " DEFAULT " + column["default"]
            if column["not_null"]:
                definition += " NOT NULL"
            columns.append(definition)
        yield f"CREATE TABLE {table_name(table)} ({','.join(columns)});"
        if table["rls"]:
            yield f"ALTER TABLE {table_name(table)} ENABLE ROW LEVEL SECURITY;"


def post_statements(metadata: dict):
    # Add foreign keys only after all tables and data exist; all are validated.
    for foreign in (False, True):
        for table in metadata["tables"]:
            for constraint in table.get("constraints") or []:
                if (constraint["type"] == "f") == foreign:
                    yield (f"ALTER TABLE {table_name(table)} ADD CONSTRAINT "
                           f"{ident(constraint['name'])} {constraint['definition']};")
    for table in metadata["tables"]:
        for index in table.get("indexes") or []:
            yield index.rstrip(";") + ";"
        for trigger in table.get("triggers") or []:
            yield trigger.rstrip(";") + ";"
    for sequence in metadata.get("sequences") or []:
        name = ident(sequence["schemaname"]) + "." + ident(sequence["sequencename"])
        value = sequence["last_value"]
        if value is not None:
            yield f"SELECT setval({literal(name)}::regclass, {value}, true);"
    yield "GRANT USAGE ON SCHEMA public TO service_role;"
    yield "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO service_role;"
    yield "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO service_role;"
    yield "REVOKE ALL ON ALL TABLES IN SCHEMA freqtrade FROM service_role;"
    yield "ALTER SCHEMA freqtrade OWNER TO freqtrade_worker;"
    for table in metadata["tables"]:
        if table["schema"] == "freqtrade":
            yield f"ALTER TABLE {table_name(table)} OWNER TO freqtrade_worker;"
    for sequence in metadata.get("sequences") or []:
        if sequence["schemaname"] == "freqtrade":
            name = ident(sequence["schemaname"]) + "." + ident(sequence["sequencename"])
            yield f"ALTER SEQUENCE {name} OWNER TO freqtrade_worker;"
    for dependency in metadata.get("sequence_dependencies") or []:
        sequence = ident(dependency["sequence_schema"]) + "." + ident(dependency["sequence_name"])
        table = ident(dependency["table_schema"]) + "." + ident(dependency["table_name"])
        yield f"ALTER SEQUENCE {sequence} OWNED BY {table}.{ident(dependency['column_name'])};"
    yield "NOTIFY pgrst, 'reload schema';"


def restore(directory: Path) -> None:
    metadata = json.loads((directory / "metadata.json").read_text())
    manifest = json.loads((directory / "manifest.json").read_text())
    if any(not table["done"] for table in manifest["tables"]):
        raise ValueError("Incomplete export")
    expected = {(t["schema"], t["name"]): t for t in manifest["tables"]}
    command = ["docker", "compose", "--env-file", str(STATE / "compose.env"),
               "-f", str(ROOT / "docker/database.compose.yml"), "exec", "-T", "db",
               "psql", "-X", "-U", "postgres", "-d", "cryptoforge", "-v", "ON_ERROR_STOP=1",
               "--single-transaction", "-f", "-"]
    with subprocess.Popen(command, stdin=subprocess.PIPE, text=True) as process:
        assert process.stdin is not None
        def write(sql):
            process.stdin.write(sql + "\n")
        try:
            write("SET TIME ZONE 'UTC'; SET search_path=public,pg_catalog;")
            for statement in schema_statements(metadata):
                write(statement)
            for table in metadata["tables"]:
                record = expected[table["schema"], table["name"]]
                for index in range(record["index"]):
                    path = directory / f"{table['schema']}.{table['name']}.{index:04}.json"
                    compressed = not path.exists()
                    if compressed:
                        path = path.with_suffix(".pgp.b64")
                    raw = path.read_text().rstrip("\n")
                    digest = hashlib.sha256(raw.encode()).hexdigest()
                    if digest != record["checksums"][index]:
                        raise ValueError(f"Snapshot checksum mismatch: {path.name}")
                    if compressed:
                        source = (f"internal.pgp_sym_decrypt(decode({literal(raw)}, 'base64'), "
                                  "'cryptoforge-transfer')::json")
                    else:
                        tag = "$cf_" + digest + "$"
                        if tag in raw:
                            raise ValueError("Unexpected SQL delimiter in snapshot")
                        source = f"{tag}{raw}{tag}::json"
                    write(f"INSERT INTO {table_name(table)} SELECT * FROM json_populate_recordset("
                          f"NULL::{table_name(table)}, {source});")
                print(f"Restoring {table['schema']}.{table['name']}: {record['count']} rows", flush=True)
            for statement in post_statements(metadata):
                write(statement)
            process.stdin.close()
            if process.wait() != 0:
                raise RuntimeError("Restore failed and transaction rolled back")
        except BaseException:
            if not process.stdin.closed:
                process.stdin.close()
            process.wait()
            raise
    print("Snapshot committed. Verify source/local row counts and content hashes before switching.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    restore(args.directory)
