"""Where observations, decisions and alerts go: JSONL on disk here; convex_sink.py and spacetime_sink.py for the cloud."""
import json
from pathlib import Path
from typing import IO, Protocol

KINDS = ("observations", "decisions", "alerts")


class Sink(Protocol):
    def write(self, kind: str, record: dict) -> None: ...

    def close(self) -> None: ...


class JsonlSink:
    """ground/out/<session>/{observations,decisions,alerts}.jsonl, appended one record per line."""

    def __init__(self, out_root: str | Path, session: str):
        if session in ("", ".", "..") or Path(session).name != session:
            raise ValueError(f"session must be a plain folder name, got {session!r}")
        self.dir = Path(out_root) / session
        self.dir.mkdir(parents=True, exist_ok=True)
        self._files: dict[str, IO[str]] = {}

    def path(self, kind: str) -> Path:
        return self.dir / f"{kind}.jsonl"

    def write(self, kind: str, record: dict) -> None:
        if kind not in KINDS:
            raise ValueError(f"unknown record kind {kind!r}")
        if kind not in self._files:
            self._files[kind] = open(self.path(kind), "a", buffering=1)
        self._files[kind].write(json.dumps(record, separators=(",", ":")) + "\n")

    def close(self) -> None:
        for f in self._files.values():
            f.close()
        self._files = {}


class MultiSink:
    def __init__(self, sinks: list[Sink]):
        self.sinks = list(sinks)

    def write(self, kind: str, record: dict) -> None:
        for sink in self.sinks:
            sink.write(kind, record)

    def close(self) -> None:
        for sink in self.sinks:
            sink.close()
