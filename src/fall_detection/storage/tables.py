"""Bounded, lossless conversion of CSV tables to compressed Parquet.

Values are stored as strings so that empty fields, integer precision, and CSI
payloads survive conversion without depending on type inference.
"""

from __future__ import annotations

import csv
import io
from .compressed import open_binary
import os
from pathlib import Path
import tempfile
from typing import Iterator


def iter_table(
    path: str | Path, *, batch_size: int = 2048
) -> Iterator[list[list[str]]]:
    """Yield rows from a CSV or string-valued Parquet table in bounded batches.

    Args:
        path: Input CSV or Parquet path.
        batch_size: Maximum rows in a yielded batch.

    Yields:
        Batches of rows in their original column order.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    path = Path(path)
    if path.suffix == ".parquet":
        import pyarrow.parquet as pq

        for batch in pq.ParquetFile(path).iter_batches(batch_size=batch_size):
            columns = batch.to_pydict()
            yield [list(row) for row in zip(*columns.values())]
    else:
        with (
            open_binary(path) as raw,
            io.TextIOWrapper(raw, encoding="utf-8", newline="") as stream,
        ):
            reader = csv.reader(stream, strict=True)
            next(reader)
            rows = []
            for row in reader:
                rows.append(row)
                if len(rows) == batch_size:
                    yield rows
                    rows = []
            if rows:
                yield rows


def convert_csv_to_parquet(source: str | Path, destination: str | Path) -> int:
    """Convert and verify a CSV table, without modifying or replacing inputs.

    Args:
        source: UTF-8 CSV file with a unique header.
        destination: New Parquet file; an existing file is never overwritten.

    Returns:
        Number of verified data rows.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    source, destination = Path(source), Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    with (
        open_binary(source) as raw,
        io.TextIOWrapper(raw, encoding="utf-8", newline="") as stream,
    ):
        header = next(csv.reader(stream, strict=True))
    if not header or len(set(header)) != len(header):
        raise ValueError("CSV header must contain unique columns")
    schema = pa.schema([(name, pa.string()) for name in header])
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    count = 0
    try:
        with pq.ParquetWriter(temporary, schema, compression="zstd") as writer:
            for rows in iter_table(source):
                if any(len(row) != len(header) for row in rows):
                    raise ValueError("CSV row does not match header width")
                columns = list(zip(*rows))
                writer.write_table(
                    pa.Table.from_arrays(
                        [pa.array(column, type=pa.string()) for column in columns],
                        schema=schema,
                    )
                )
                count += len(rows)
        from itertools import chain, zip_longest

        original = chain.from_iterable(iter_table(source))
        # The temporary filename is not a format indicator.
        batches = pq.ParquetFile(temporary).iter_batches(batch_size=2048)
        converted = (
            list(row) for batch in batches for row in zip(*batch.to_pydict().values())
        )
        sentinel = object()
        if any(a != b for a, b in zip_longest(original, converted, fillvalue=sentinel)):
            raise ValueError("Parquet verification failed")
        # Linking publishes atomically and refuses to replace a concurrent output.
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return count
