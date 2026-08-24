#!/usr/bin/env python3

# Converts the OS Open USRN GeoPackage (British National Grid) into a
# parquet file of USRN -> WGS84 street centreline geometry (as GeoJSON),
# for drawing streets on the Leaflet maps.

from pathlib import Path

import duckdb

GPKG_FILE = Path("cache/osopenusrn.gpkg")
GPKG_LAYER = "openUSRN"
PARQUET_FILE = Path("database/open_usrn.parquet")


def main():
    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")
    con.execute(
        f"""
        COPY (
            SELECT usrn AS USRN,
                   ST_AsGeoJSON(ST_Force2D(ST_ReducePrecision(
                       ST_Transform(geometry, 'EPSG:27700', 'EPSG:4326', always_xy := true), 0.000001
                   ))) AS GEOMETRY_GEOJSON
            FROM ST_Read('{GPKG_FILE}', layer='{GPKG_LAYER}')
        ) TO '{PARQUET_FILE}' (FORMAT PARQUET)
        """
    )
    con.close()


if __name__ == "__main__":
    main()
