import csv

import pytest

from fall_detection.storage.tables import convert_csv_to_parquet, iter_table


def test_convert_preserves_rows_and_original(tmp_path):
    source = tmp_path / "csi.csv"
    rows = [["00001", "", "[1,-2,3]"], ["99999999999999999999", "x,y", "[]"]]
    with source.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["id", "value", "data"])
        writer.writerows(rows)
    original = source.read_bytes()
    destination = tmp_path / "csi.parquet"
    assert convert_csv_to_parquet(source, destination) == 2
    assert list(iter_table(destination, batch_size=1)) == [[rows[0]], [rows[1]]]
    assert source.read_bytes() == original
    with pytest.raises(FileExistsError):
        convert_csv_to_parquet(source, destination)


def test_convert_rejects_malformed_rows_without_publishing(tmp_path):
    source = tmp_path / "csi.csv"
    source.write_text("a,b\n1,2,3\n", encoding="utf-8")
    destination = tmp_path / "csi.parquet"
    with pytest.raises(ValueError, match="width"):
        convert_csv_to_parquet(source, destination)
    assert not destination.exists()
