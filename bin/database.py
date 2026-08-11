#!/usr/bin/env python3

# Creates a duckdb database file with a view onto each parquet table, for
# exploring the AddressBase data with the duckdb CLI or client libraries.

from pathlib import Path

import duckdb

DATASET_DIR = Path("database")
DATABASE_FILE = DATASET_DIR / "addressbase.duckdb"


def main():
    con = duckdb.connect(str(DATABASE_FILE))
    for parquet_path in sorted(DATASET_DIR.glob("*.parquet")):
        name = parquet_path.stem
        con.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_parquet('{parquet_path}')")
    con.close()


if __name__ == "__main__":
    main()
