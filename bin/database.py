#!/usr/bin/env python3

# Creates a duckdb database file with a view onto each parquet table, for
# exploring the AddressBase data with the duckdb CLI or client libraries.

from pathlib import Path

import duckdb

DATASET_DIR = Path("database")
DATABASE_FILE = DATASET_DIR / "addressbase.duckdb"
CLASSIFICATION_SCHEME_CSV = DATASET_DIR / "addressbase-classification.csv"
CUSTODIAN_LOOKUP_CSV = DATASET_DIR / "addressbase-custodian.csv"


def main():
    con = duckdb.connect(str(DATABASE_FILE))
    for parquet_path in sorted(DATASET_DIR.glob("*.parquet")):
        name = parquet_path.stem
        con.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_parquet('{parquet_path}')")
    con.execute(
        f"CREATE OR REPLACE VIEW classification_scheme AS "
        f"SELECT * FROM read_csv('{CLASSIFICATION_SCHEME_CSV}')"
    )
    con.execute(
        f"CREATE OR REPLACE VIEW custodian_lookup AS SELECT * FROM read_csv('{CUSTODIAN_LOOKUP_CSV}')"
    )
    # planning.data.gov.uk's organisation dataset only names English custodians,
    # so for the rest (Wales, Scotland, and any it doesn't recognise) fall back
    # to the administrative area most commonly used by streets in that custodian
    con.execute("""
        CREATE OR REPLACE TABLE custodian AS
        WITH area AS (
            SELECT b.LOCAL_CUSTODIAN_CODE, sd.ADMINISTRATIVE_AREA AS NAME
            FROM blpu b
            JOIN lpi l ON l.UPRN = b.UPRN
            JOIN street_descriptor sd ON sd.USRN = l.USRN
            GROUP BY b.LOCAL_CUSTODIAN_CODE, sd.ADMINISTRATIVE_AREA
            QUALIFY ROW_NUMBER() OVER (PARTITION BY b.LOCAL_CUSTODIAN_CODE ORDER BY COUNT(*) DESC) = 1
        )
        SELECT area.LOCAL_CUSTODIAN_CODE, COALESCE(lookup.NAME, area.NAME) AS NAME
        FROM area
        LEFT JOIN custodian_lookup lookup
            ON CAST(lookup.LOCAL_CUSTODIAN_CODE AS BIGINT) = area.LOCAL_CUSTODIAN_CODE
    """)
    con.close()


if __name__ == "__main__":
    main()
