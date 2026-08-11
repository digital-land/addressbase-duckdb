#!/usr/bin/env python3

# AddressBase Premium's CSV export is one flat file per volume, with every
# record type (STREET, BLPU, LPI, ...) interleaved and identified by a
# RECORD_IDENTIFIER in the first column - each type has a different number
# of columns, so it can't be loaded with a single read_csv(). This script
# splits the export into one CSV per record type, then loads each into a
# parquet file in the database directory using duckdb's CSV type inference.

import csv
import io
import sys
from pathlib import Path
from zipfile import ZipFile

import duckdb

SOURCE_ZIP = Path("cache/AB76GB_CSV.zip")
HEADERS_ZIP = Path("cache/addressbase-premium-header-files.zip")
SPLIT_DIR = Path("var/addressbase")
DATASET_DIR = Path("database")

# record types worth keeping as parquet tables; 10 (HEADER) and 99
# (TRAILER) are per-volume bookkeeping rather than gazetteer data
RECORD_TYPES = {
    "11": "street",
    "15": "street_descriptor",
    "21": "blpu",
    "23": "xref",
    "24": "lpi",
    "28": "delivery_point_address",
    "29": "metadata",
    "30": "successor",
    "31": "organisation",
    "32": "classification",
}


def header_row(zip_file, code):
    member = next(n for n in zip_file.namelist() if n.startswith(f"Record_{code}_"))
    with zip_file.open(member) as f:
        return next(csv.reader(io.TextIOWrapper(f, encoding="utf-8-sig")))


def split_by_record_type():
    SPLIT_DIR.mkdir(parents=True, exist_ok=True)

    with ZipFile(HEADERS_ZIP) as headers_zip:
        files = {code: open(SPLIT_DIR / f"{name}.csv", "w", newline="") for code, name in RECORD_TYPES.items()}
        writers = {code: csv.writer(f) for code, f in files.items()}
        for code, writer in writers.items():
            writer.writerow(header_row(headers_zip, code))

    with ZipFile(SOURCE_ZIP) as source_zip:
        members = [n for n in source_zip.namelist() if n.endswith(".csv")]
        for i, member in enumerate(members, 1):
            with source_zip.open(member) as f:
                for row in csv.reader(io.TextIOWrapper(f, encoding="utf-8-sig")):
                    writer = writers.get(row[0])
                    if writer:
                        writer.writerow(row)
            print(f"split {i}/{len(members)}: {member}", file=sys.stderr)

    for f in files.values():
        f.close()


def load_into_parquet():
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    for code, name in RECORD_TYPES.items():
        csv_path = SPLIT_DIR / f"{name}.csv"
        parquet_path = DATASET_DIR / f"{name}.parquet"
        print(f"writing {parquet_path}", file=sys.stderr)
        con.execute(
            f"""
            COPY (SELECT * FROM read_csv_auto('{csv_path}', sample_size=-1))
            TO '{parquet_path}' (FORMAT PARQUET, COMPRESSION ZSTD)
            """
        )
        csv_path.unlink()


if __name__ == "__main__":
    split_by_record_type()
    load_into_parquet()
    SPLIT_DIR.rmdir()
