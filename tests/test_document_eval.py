from pathlib import Path
from types import SimpleNamespace

from cryptoforge.document_eval import (
    Dimension,
    Document,
    Rubric,
    discover_documents,
    evaluate_document,
    results_to_json,
    table,
)


class FakeClient:
    def system_one(self, state, questions):  # type: ignore[no-untyped-def]
        assert "document" in state
        assert set(questions) == {"clarity", "risk"}
        return SimpleNamespace(
            scores={
                "clarity": SimpleNamespace(
                    score=2.0,
                    confidence=0.75,
                    probabilities={"0": 0.0, "1": 0.0, "2": 1.0},
                ),
                "risk": SimpleNamespace(
                    score=1.25,
                    confidence=0.5,
                    probabilities={"0": 0.0, "1": 0.75, "2": 0.25},
                ),
            },
            usage=SimpleNamespace(input_tokens=100, output_tokens=20),
        )


def sample_rubric() -> Rubric:
    return Rubric(
        model="jev-latest",
        dimensions=(
            Dimension(
                id="clarity",
                label="Clarity",
                instructions="How clear is the document?",
                levels=("unclear", "somewhat clear", "clear"),
            ),
            Dimension(
                id="risk",
                label="Risk awareness",
                instructions="How aware is the document of risks?",
                levels=("none", "some", "strong"),
            ),
        ),
    )


def test_discover_documents_reads_files_and_skips_empty(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("hello", encoding="utf-8")
    (tmp_path / "b.txt").write_text("  ", encoding="utf-8")
    (tmp_path / "c.json").write_text("{}", encoding="utf-8")

    documents = discover_documents([tmp_path])

    assert [item.id for item in documents] == ["a"]
    assert documents[0].text == "hello"


def test_evaluate_document_maps_score_answers() -> None:
    result = evaluate_document(
        FakeClient(),
        Document(id="doc", path=Path("doc.md"), text="A clear doc."),
        sample_rubric(),
    )

    assert result.document_id == "doc"
    assert result.input_tokens == 100
    assert len(result.dimensions) == 2
    assert result.dimensions[0].normalized_score == 1.0
    assert result.average_normalized_score == 0.8125


def test_result_renderers() -> None:
    result = evaluate_document(
        FakeClient(),
        Document(id="doc", path=Path("doc.md"), text="A clear doc."),
        sample_rubric(),
    )

    rendered_json = results_to_json([result])
    rendered_table = table([result])

    assert '"document_id": "doc"' in rendered_json
    assert "Clarity" in rendered_table
