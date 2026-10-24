import json

import pytest

from sinks import ConvexSink, JsonlSink, MultiSink, SpacetimeSink


def read_lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_jsonl_sink_writes_one_file_per_kind(tmp_path):
    sink = JsonlSink(tmp_path, "20261024-153000")
    sink.write("observations", {"t": 1})
    sink.write("observations", {"t": 2})
    sink.write("decisions", {"agent": "pricing"})
    sink.write("alerts", {"status": "needs_review"})
    sink.close()
    session = tmp_path / "20261024-153000"
    assert read_lines(session / "observations.jsonl") == [{"t": 1}, {"t": 2}]
    assert read_lines(session / "decisions.jsonl") == [{"agent": "pricing"}]
    assert read_lines(session / "alerts.jsonl") == [{"status": "needs_review"}]


def test_jsonl_sink_appends_across_runs(tmp_path):
    for t in (1, 2):
        sink = JsonlSink(tmp_path, "s")
        sink.write("observations", {"t": t})
        sink.close()
    assert len(read_lines(tmp_path / "s" / "observations.jsonl")) == 2


def test_unknown_kind_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        JsonlSink(tmp_path, "s").write("prices", {})


def test_multi_sink_fans_out(tmp_path):
    a, b = JsonlSink(tmp_path / "a", "s"), JsonlSink(tmp_path / "b", "s")
    multi = MultiSink([a, b])
    multi.write("alerts", {"x": 1})
    multi.close()
    assert read_lines(tmp_path / "a" / "s" / "alerts.jsonl") == read_lines(tmp_path / "b" / "s" / "alerts.jsonl")


@pytest.mark.parametrize("cls", [ConvexSink, SpacetimeSink])
def test_cloud_sinks_are_explicit_stubs(cls):
    with pytest.raises(NotImplementedError):
        cls().write("observations", {})
