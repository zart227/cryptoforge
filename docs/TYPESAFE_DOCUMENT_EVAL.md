# TypeSafe Document Evaluation CLI

CryptoForge includes a small CLI for evaluating text documents across
multiple rubric dimensions with the TypeSafe System One API.

## TypeSafe Design

The CLI sends one document as structured TypeSafe `state`:

```json
{
  "document": {
    "id": "example",
    "path": "docs/example.md",
    "text": "..."
  }
}
```

Each rubric dimension is one independent TypeSafe `Score` question over
that same state. This follows the TypeSafe guidance to keep code in
control, ask narrow independent questions together, and combine typed
answers in ordinary application logic.

## Configuration

Default rubric:

- `config/typesafe_document_rubric.json`

The default dimensions are:

- clarity
- evidence quality
- actionability
- risk awareness
- implementation readiness

Each dimension has 4 ordered score levels. You can supply another rubric
with `--rubric`.

## Setup

Install the optional TypeSafe dependency:

```text
.venv/bin/python -m pip install -e '.[typesafe]'
```

Set your API key:

```text
export TYPESAFE_API_KEY='...'
```

The CLI exits with code `2` before making requests when
`TYPESAFE_API_KEY` is not set.

## Usage

Evaluate files or directories:

```text
.venv/bin/python -m cryptoforge.document_eval_cli docs README.md
```

Write machine-readable outputs:

```text
.venv/bin/python -m cryptoforge.document_eval_cli docs \
  --json-out document-scores.json \
  --csv-out document-scores.csv
```

Print JSON instead of a table:

```text
.venv/bin/python -m cryptoforge.document_eval_cli docs --format json
```

The CLI scans `.md` and `.txt` files by default.

## Output

For each document and dimension, results include:

- score
- maximum score
- normalized score
- confidence
- level probabilities
- request token usage when reported

Low confidence should be treated as a review signal, not as failure by
itself.
