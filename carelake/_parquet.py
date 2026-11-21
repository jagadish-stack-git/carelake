"""Buffered parquet output and row-wise input, so a cohort streams through."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq


class RowGroupWriter:
    def __init__(self, path: Path, schema: pa.Schema, group_size: int = 40_000):
        self.path, self.schema, self.group_size = path, schema, group_size
        self._buf: list[dict[str, Any]] = []
        self._w: pq.ParquetWriter | None = None
        self.written = 0

    def put(self, row: dict[str, Any]) -> None:
        self._buf.append(row)
        if len(self._buf) >= self.group_size:
            self._drain()

    def _drain(self) -> None:
        if not self._buf:
            return
        if self._w is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._w = pq.ParquetWriter(self.path, self.schema, compression="zstd")
        self._w.write_table(pa.Table.from_pylist(self._buf, schema=self.schema))
        self.written += len(self._buf)
        self._buf = []

    def finish(self) -> int:
        """Always leaves a file, even an empty one, so globs downstream resolve."""
        self._drain()
        if self._w is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            pq.write_table(self.schema.empty_table(), self.path, compression="zstd")
        else:
            self._w.close()
        return self.written


def rows(path: Path, columns: list[str] | None = None) -> Iterator[dict[str, Any]]:
    for batch in pq.ParquetFile(path).iter_batches(batch_size=40_000, columns=columns):
        yield from batch.to_pylist()
