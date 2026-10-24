"""Where observations, decisions and alerts go. JSONL on disk now; Convex and Spacetime later."""
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


class ConvexSink:
    """TODO: push observations to Convex `observations`, prices and decisions to `prices`/`decisions`,
    alerts to `alerts` (see docs/architecture.md section 4). Needs `npx convex login` and the deployment URL."""

    def write(self, kind: str, record: dict) -> None:
        raise NotImplementedError("ConvexSink is not built yet")

    def close(self) -> None:
        raise NotImplementedError("ConvexSink is not built yet")


class SpacetimeSink:
    """TODO: post settlement values and market proposals to the Spacetime market module (market/)."""

    def write(self, kind: str, record: dict) -> None:
        raise NotImplementedError("SpacetimeSink is not built yet")

    def close(self) -> None:
        raise NotImplementedError("SpacetimeSink is not built yet")


class MultiSink:
    def __init__(self, sinks: list[Sink]):
        self.sinks = list(sinks)

    def write(self, kind: str, record: dict) -> None:
        for sink in self.sinks:
            sink.write(kind, record)

    def close(self) -> None:
        for sink in self.sinks:
            sink.close()
