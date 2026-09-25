from __future__ import annotations

from dataclasses import dataclass
import csv
import json
from pathlib import Path
from typing import Any, Protocol


DEFAULT_EXTENSIONS = (".md", ".txt")
DEFAULT_RUBRIC_PATH = Path("config/typesafe_document_rubric.json")


class TypeSafeLikeClient(Protocol):
    def system_one(self, state: Any, questions: dict[str, Any]) -> Any:
        ...


@dataclass(frozen=True)
class Dimension:
    id: str
    label: str
    instructions: str
    levels: tuple[str, ...]

    def validate(self) -> None:
        if not self.id.replace("_", "").replace("-", "").isalnum():
            raise ValueError(f"Dimension id must be CLI-safe: {self.id!r}")
        if len(self.levels) < 2:
            raise ValueError(f"Dimension {self.id!r} must define at least two score levels")
        if len(self.levels) > 10:
            raise ValueError(f"Dimension {self.id!r} must define no more than 10 score levels")


@dataclass(frozen=True)
class Rubric:
    model: str
    dimensions: tuple[Dimension, ...]

    def validate(self) -> None:
        if not self.dimensions:
            raise ValueError("Rubric must define at least one dimension")
        seen: set[str] = set()
        for dimension in self.dimensions:
            dimension.validate()
            if dimension.id in seen:
                raise ValueError(f"Duplicate dimension id: {dimension.id}")
            seen.add(dimension.id)


@dataclass(frozen=True)
class Document:
    id: str
    path: Path
    text: str


@dataclass(frozen=True)
class DimensionResult:
    id: str
    label: str
    score: float
    max_score: int
    normalized_score: float
    confidence: float
    probabilities: dict[str, float]


@dataclass(frozen=True)
class DocumentResult:
    document_id: str
    path: str
    dimensions: tuple[DimensionResult, ...]
    input_tokens: int | None = None
    output_tokens: int | None = None
    error: str | None = None

    @property
    def average_normalized_score(self) -> float | None:
        if not self.dimensions:
            return None
        return sum(item.normalized_score for item in self.dimensions) / len(self.dimensions)


def load_rubric(path: Path = DEFAULT_RUBRIC_PATH) -> Rubric:
    raw = json.loads(path.read_text(encoding="utf-8"))
    dimensions = tuple(
        Dimension(
            id=str(item["id"]),
            label=str(item.get("label") or item["id"]),
            instructions=str(item["instructions"]),
            levels=tuple(str(level) for level in item["levels"]),
        )
        for item in raw["dimensions"]
    )
    rubric = Rubric(model=str(raw.get("model", "jev-latest")), dimensions=dimensions)
    rubric.validate()
    return rubric


def discover_documents(paths: list[Path], extensions: tuple[str, ...] = DEFAULT_EXTENSIONS) -> list[Document]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(
                item
                for item in sorted(path.rglob("*"))
                if item.is_file() and item.suffix.lower() in extensions
            )
        elif path.is_file():
            files.append(path)
        else:
            raise FileNotFoundError(f"Document path does not exist: {path}")

    documents: list[Document] = []
    for file_path in files:
        text = file_path.read_text(encoding="utf-8")
        if text.strip():
            documents.append(Document(id=file_path.stem, path=file_path, text=text))
    return documents


def build_score_questions(rubric: Rubric) -> dict[str, Any]:
    from typesafe_sdk import Score

    return {
        dimension.id: Score(
            instructions={
                "question": dimension.instructions,
                "document_reference": "Evaluate `document.text`; use `document.path` only as identity/context.",
            },
            criteria=list(dimension.levels),
        )
        for dimension in rubric.dimensions
    }


def evaluate_document(client: TypeSafeLikeClient, document: Document, rubric: Rubric) -> DocumentResult:
    state = {
        "document": {
            "id": document.id,
            "path": str(document.path),
            "text": document.text,
        }
    }
    questions = build_score_questions(rubric)
    response = client.system_one(state, questions)
    scores = getattr(response, "scores", {})

    dimensions: list[DimensionResult] = []
    for dimension in rubric.dimensions:
        answer = scores[dimension.id]
        score = float(answer.score)
        max_score = len(dimension.levels) - 1
        normalized = score / max_score if max_score else 0.0
        dimensions.append(
            DimensionResult(
                id=dimension.id,
                label=dimension.label,
                score=score,
                max_score=max_score,
                normalized_score=normalized,
                confidence=float(answer.confidence),
                probabilities={str(key): float(value) for key, value in answer.probabilities.items()},
            )
        )

    usage = getattr(response, "usage", None)
    return DocumentResult(
        document_id=document.id,
        path=str(document.path),
        dimensions=tuple(dimensions),
        input_tokens=getattr(usage, "input_tokens", None),
        output_tokens=getattr(usage, "output_tokens", None),
    )


def evaluate_documents(
    documents: list[Document],
    rubric: Rubric,
    *,
    model: str | None = None,
    continue_on_error: bool = True,
) -> list[DocumentResult]:
    from typesafe_sdk import TypeSafeAPIError, TypeSafeClient

    selected_model = model or rubric.model
    results: list[DocumentResult] = []
    with TypeSafeClient(model=selected_model) as client:
        for document in documents:
            try:
                results.append(evaluate_document(client, document, rubric))
            except TypeSafeAPIError as exc:
                if not continue_on_error:
                    raise
                results.append(
                    DocumentResult(
                        document_id=document.id,
                        path=str(document.path),
                        dimensions=(),
                        error=f"TypeSafe API error {getattr(exc, 'status', 'unknown')}: {exc}",
                    )
                )
    return results


def results_to_json(results: list[DocumentResult]) -> str:
    return json.dumps([result_to_dict(result) for result in results], indent=2, sort_keys=True)


def result_to_dict(result: DocumentResult) -> dict[str, Any]:
    return {
        "document_id": result.document_id,
        "path": result.path,
        "average_normalized_score": result.average_normalized_score,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "error": result.error,
        "dimensions": [
            {
                "id": dimension.id,
                "label": dimension.label,
                "score": dimension.score,
                "max_score": dimension.max_score,
                "normalized_score": dimension.normalized_score,
                "confidence": dimension.confidence,
                "probabilities": dimension.probabilities,
            }
            for dimension in result.dimensions
        ],
    }


def write_csv(results: list[DocumentResult], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "document_id",
                "path",
                "dimension_id",
                "dimension_label",
                "score",
                "max_score",
                "normalized_score",
                "confidence",
                "input_tokens",
                "output_tokens",
                "error",
            ],
        )
        writer.writeheader()
        for result in results:
            if not result.dimensions:
                writer.writerow(
                    {
                        "document_id": result.document_id,
                        "path": result.path,
                        "error": result.error,
                    }
                )
                continue
            for dimension in result.dimensions:
                writer.writerow(
                    {
                        "document_id": result.document_id,
                        "path": result.path,
                        "dimension_id": dimension.id,
                        "dimension_label": dimension.label,
                        "score": f"{dimension.score:.4f}",
                        "max_score": dimension.max_score,
                        "normalized_score": f"{dimension.normalized_score:.4f}",
                        "confidence": f"{dimension.confidence:.4f}",
                        "input_tokens": result.input_tokens,
                        "output_tokens": result.output_tokens,
                        "error": result.error,
                    }
                )


def table(results: list[DocumentResult]) -> str:
    rows = [["document", "avg", "dimension", "score", "confidence"]]
    for result in results:
        if result.error:
            rows.append([result.document_id, "ERR", result.error, "", ""])
            continue
        avg = "" if result.average_normalized_score is None else f"{result.average_normalized_score:.2f}"
        for dimension in result.dimensions:
            rows.append(
                [
                    result.document_id,
                    avg,
                    dimension.label,
                    f"{dimension.score:.2f}/{dimension.max_score}",
                    f"{dimension.confidence:.2f}",
                ]
            )
    widths = [max(len(str(row[index])) for row in rows) for index in range(len(rows[0]))]
    lines = []
    for row_index, row in enumerate(rows):
        line = "  ".join(str(value).ljust(widths[index]) for index, value in enumerate(row))
        lines.append(line)
        if row_index == 0:
            lines.append("  ".join("-" * width for width in widths))
    return "\n".join(lines)
