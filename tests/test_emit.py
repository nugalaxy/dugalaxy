"""Tests for the disk-backed emitters — Milestone 4."""

import json
from pathlib import Path

import yaml

from dugalaxy.emit import IndexEmitter, JsonlEmitter, Sample, YamlEmitter

NASTY = 'cmd "q" \\ end\nNEXT line'


def _conversation(index: int) -> Sample:
    return Sample(
        index=index,
        session_id=f"demo_{index:02d}",
        kind="conversation",
        turns=(("user", f"alert {NASTY}"), ("agent", "analysis here")),
        document=None,
        facts={"proc": "powershell.exe", "n": index},
        seed=42,
    )


# ── JSONL ─────────────────────────────────────────────────────────────────────


def test_jsonl_one_object_per_line(tmp_path: Path) -> None:
    path = tmp_path / "out.jsonl"
    with JsonlEmitter(path) as emitter:
        emitter.emit(_conversation(0))
        emitter.emit(_conversation(1))

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["session_id"] == "demo_00"
    assert first["turns"][0]["role"] == "user"
    assert first["turns"][1]["role"] == "agent"
    # nasty characters round-trip exactly
    assert NASTY in first["turns"][0]["content"]


def test_jsonl_document_dict_is_the_line(tmp_path: Path) -> None:
    path = tmp_path / "docs.jsonl"
    sample = Sample(
        index=0,
        session_id="d_00",
        kind="document",
        turns=(),
        document={"event": "login", "cmd": NASTY},
        facts={},
        seed=1,
    )
    with JsonlEmitter(path) as emitter:
        emitter.emit(sample)
    record = json.loads(path.read_text(encoding="utf-8").strip())
    assert record == {"event": "login", "cmd": NASTY}


def test_jsonl_include_meta(tmp_path: Path) -> None:
    path = tmp_path / "out.jsonl"
    with JsonlEmitter(path, include_meta=True) as emitter:
        emitter.emit(_conversation(3))
    record = json.loads(path.read_text(encoding="utf-8").strip())
    assert record["_meta"]["index"] == 3
    assert record["_meta"]["seed"] == 42
    assert record["_meta"]["facts"]["proc"] == "powershell.exe"


# ── YAML envelope ─────────────────────────────────────────────────────────────


def test_yaml_envelope_is_valid_and_ingestible(tmp_path: Path) -> None:
    path = tmp_path / "out.yaml"
    with YamlEmitter(
        path, dataset_name="demo-set", description="a demo", kind="conversation"
    ) as emitter:
        emitter.emit(_conversation(0))
        emitter.emit(_conversation(1))

    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert loaded["version"] == "1.0"
    assert loaded["dataset_name"] == "demo-set"
    assert loaded["description"] == "a demo"
    assert len(loaded["conversations"]) == 2

    conv = loaded["conversations"][0]
    assert conv["session_id"] == "demo_00"
    assert [t["role"] for t in conv["turns"]] == ["user", "agent"]
    # nasty characters survived YAML serialization
    assert NASTY in conv["turns"][0]["content"]


def test_yaml_multiline_content_uses_block_literals(tmp_path: Path) -> None:
    """Multi-line turns render as block scalars (|) on the real streamed+indented file.

    The risk lives in the hand-indentation: each dumped item is re-indented under the
    list key with textwrap.indent, and block scalars are indentation-sensitive. So the
    proof has to be the final emitted file, not yaml.dump in isolation.
    """
    user_content = (
        "Hi, I'm Emily with a login issue. Here is my ticket:\n"
        "```json\n"
        "{\n"
        '  "ticket_id": "TICKET-8739",\n'
        '  "product": "Nimbus CLI"\n'
        "}\n"
        "```\n"
        "Can you help?"
    )
    agent_content = "First paragraph of the reply.\n\nSecond paragraph after a blank line."

    samples = [
        Sample(
            index=i,
            session_id=f"demo_{i:02d}",
            kind="conversation",
            turns=(("user", user_content), ("agent", agent_content)),
            document=None,
            facts={},
            seed=7,
        )
        for i in range(2)
    ]

    path = tmp_path / "blocks.yaml"
    with YamlEmitter(path, dataset_name="d", description="", kind="conversation") as emitter:
        for sample in samples:
            emitter.emit(sample)

    raw = path.read_text(encoding="utf-8")
    # (a) multi-line content is rendered as block literals: real newlines, no \n escapes.
    assert "content: |" in raw
    assert "\\n" not in raw
    assert '"ticket_id": "TICKET-8739"' in raw  # embedded JSON shows up unescaped

    # (b) the whole file round-trips byte-for-byte across multiple appended items.
    loaded = yaml.safe_load(raw)
    assert len(loaded["conversations"]) == 2
    for conv in loaded["conversations"]:
        assert [t["role"] for t in conv["turns"]] == ["user", "agent"]
        assert conv["turns"][0]["content"] == user_content
        assert conv["turns"][1]["content"] == agent_content


def test_yaml_empty_run_is_valid_empty_list(tmp_path: Path) -> None:
    path = tmp_path / "empty.yaml"
    with YamlEmitter(path, dataset_name="d", description="", kind="conversation"):
        pass
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert loaded["conversations"] == []


def test_yaml_document_envelope(tmp_path: Path) -> None:
    path = tmp_path / "docs.yaml"
    sample = Sample(
        index=0,
        session_id="d_00",
        kind="document",
        turns=(),
        document={"event": "login"},
        facts={},
        seed=1,
    )
    with YamlEmitter(path, dataset_name="d", description="", kind="document") as emitter:
        emitter.emit(sample)
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert loaded["documents"][0]["event"] == "login"


# ── index ─────────────────────────────────────────────────────────────────────


def test_index_records_each_sample(tmp_path: Path) -> None:
    path = tmp_path / "index.jsonl"
    with IndexEmitter(path) as emitter:
        emitter.emit(_conversation(0))
        emitter.emit(_conversation(1))
    entries = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [e["session_id"] for e in entries] == ["demo_00", "demo_01"]
    assert all(e["seed"] == 42 for e in entries)


def test_emitters_write_incrementally(tmp_path: Path) -> None:
    """Each sample must hit disk as it is emitted, not buffered until close."""
    path = tmp_path / "out.jsonl"
    with JsonlEmitter(path) as emitter:
        emitter.emit(_conversation(0))
        # The first line is already on disk before the context closes.
        assert path.read_text(encoding="utf-8").count("\n") == 1
        emitter.emit(_conversation(1))
        assert path.read_text(encoding="utf-8").count("\n") == 2
