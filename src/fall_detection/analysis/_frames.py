"""Conversion of analysis tables from pandas to polars at module boundaries."""

from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    import pandas as pd


def as_polars(frame: "pl.DataFrame | pd.DataFrame") -> pl.DataFrame:
    """Return a polars frame, converting a pandas frame at the module boundary.

    NaN values become nulls, so polars reductions skip missing values.

    Args:
        frame: A polars frame, or a pandas frame such as the one returned by
            ``AnalysisSession.read_packets``.

    Returns:
        ``frame`` unchanged when it is already polars; otherwise its conversion.
    """
    return (
        frame
        if isinstance(frame, pl.DataFrame)
        else pl.from_pandas(frame, nan_to_null=True)
    )
