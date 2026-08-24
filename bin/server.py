#!/usr/bin/env python3

# Simple web viewer over the duckdb database: look up every row related to a
# UPRN or a USRN across all tables, cross-linked via the LPI table (which
# maps UPRN to USRN).

import html
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

import duckdb

DATABASE_FILE = Path("database/addressbase.duckdb")
PORT = 8002

UPRN_TABLES = ["blpu", "lpi", "classification", "delivery_point_address", "organisation", "xref", "successor"]
USRN_TABLES = ["street", "street_descriptor"]

SAO_FIELDS = ["SAO_START_NUMBER", "SAO_START_SUFFIX", "SAO_END_NUMBER", "SAO_END_SUFFIX", "SAO_TEXT"]
PAO_FIELDS = ["PAO_START_NUMBER", "PAO_START_SUFFIX", "PAO_END_NUMBER", "PAO_END_SUFFIX", "PAO_TEXT"]
DELIVERY_ADDRESS_FIELDS = [
    "ORGANISATION_NAME",
    "DEPARTMENT_NAME",
    "SUB_BUILDING_NAME",
    "BUILDING_NAME",
    "BUILDING_NUMBER",
    "DEPENDENT_THOROUGHFARE",
    "THOROUGHFARE",
    "DOUBLE_DEPENDENT_LOCALITY",
    "DEPENDENT_LOCALITY",
    "POST_TOWN",
    "POSTCODE",
]

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
body {{ font-family: sans-serif; margin: 2em; }}
table {{ border-collapse: collapse; margin-bottom: 2em; }}
th, td {{ border: 1px solid #ccc; padding: 4px 8px; font-size: 0.85em; }}
th {{ background: #eee; text-align: left; }}
form {{ margin-bottom: 0.5em; }}
input {{ font-size: 1em; padding: 4px; }}
#map {{ width: 100%; height: 300px; border: 1px solid black; margin-bottom: 1em; }}
</style></head>
<body>
<h1><a href="/">AddressBase</a></h1>
{forms}{body}
</body></html>
"""

SEARCH_FORMS = """<form action="/uprn" method="get"><label>UPRN <input name="q" autofocus></label> <button>search</button></form>
<form action="/usrn" method="get"><label>USRN <input name="q"></label> <button>search</button></form>
<form action="/postcode" method="get"><label>postcode <input name="q"></label> <button>search</button></form>
<form action="/udprn" method="get"><label>UDPRN <input name="q"></label> <button>search</button></form>
"""


def query_rows(con, table, column, value):
    cols = [row[0] for row in con.execute(f"DESCRIBE {table}").fetchall()]
    if column not in cols:
        return cols, []
    rows = con.execute(f"SELECT * FROM {table} WHERE CAST({column} AS VARCHAR) = ?", [value]).fetchall()
    return cols, rows


def add_classification_descriptions(con, cols, rows):
    if "CLASS_SCHEME" not in cols or "CLASSIFICATION_CODE" not in cols:
        return cols, rows
    scheme_i, code_i = cols.index("CLASS_SCHEME"), cols.index("CLASSIFICATION_CODE")
    new_rows = []
    for row in rows:
        desc = con.execute(
            "SELECT DESCRIPTION FROM classification_scheme WHERE CLASS_SCHEME = ? AND CLASSIFICATION_CODE = ?",
            [row[scheme_i], row[code_i]],
        ).fetchone()
        new_rows.append(row + (desc[0] if desc else None,))
    return cols + ["DESCRIPTION"], new_rows


def add_custodian_names(con, cols, rows):
    if "LOCAL_CUSTODIAN_CODE" not in cols:
        return cols, rows
    code_i = cols.index("LOCAL_CUSTODIAN_CODE")
    new_rows = []
    for row in rows:
        name = con.execute(
            "SELECT NAME FROM custodian WHERE LOCAL_CUSTODIAN_CODE = ?", [row[code_i]]
        ).fetchone()
        new_rows.append(row + (name[0] if name else None,))
    return cols + ["CUSTODIAN_NAME"], new_rows


def normalize_postcode(postcode):
    postcode = postcode.strip().upper().replace(" ", "")
    if len(postcode) > 3:
        postcode = postcode[:-3] + " " + postcode[-3:]
    return postcode


def render_cell(col, v):
    if v is None:
        return ""
    text = html.escape(str(v))
    if col == "USRN":
        return f'<a href="/usrn/{text}">{text}</a>'
    if col == "UPRN":
        return f'<a href="/uprn/{text}">{text}</a>'
    if col == "UDPRN":
        return f'<a href="/udprn/{text}">{text}</a>'
    if col in ("POSTCODE_LOCATOR", "POSTCODE"):
        return f'<a href="/postcode/{quote(str(v))}">{text}</a>'
    return text


def join_fields(cols, row, fields, sep=" "):
    return sep.join(str(row[cols.index(f)]) for f in fields if row[cols.index(f)] not in (None, ""))


def field_by_uprn(con, table, uprns, fields, sep=" "):
    cols = [row[0] for row in con.execute(f"DESCRIBE {table}").fetchall()]
    rows = con.execute(
        f"SELECT * FROM {table} WHERE UPRN IN ({','.join('?' * len(uprns))})", uprns
    ).fetchall()
    uprn_i = cols.index("UPRN")
    result = {}
    for row in rows:
        result.setdefault(row[uprn_i], join_fields(cols, row, fields, sep))
    return result


def render_table(name, cols, rows):
    if not rows:
        return ""
    head = "".join(f"<th>{html.escape(c)}</th>" for c in cols)
    body = "".join(
        "<tr>" + "".join(f"<td>{render_cell(c, v)}</td>" for c, v in zip(cols, row)) + "</tr>"
        for row in rows
    )
    return f"<h2>{html.escape(name)}</h2><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_map(points):
    points = [p for p in points if p[0] is not None and p[1] is not None]
    if not points:
        return ""
    markers = json.dumps(
        [{"lat": lat, "lon": lon, "label": label, "color": color} for lat, lon, label, color in points]
    )
    return f"""<div id="map"></div>
<script>
(function() {{
  var points = {markers};
  var map = L.map('map');
  L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    attribution: '&copy; OpenStreetMap contributors'
  }}).addTo(map);
  var markers = points.map(function(p) {{
    var color = p.color || '#3388ff';
    var marker = L.circleMarker([p.lat, p.lon], {{radius: 4, color: color, fillColor: color, fillOpacity: 0.9}});
    return marker.addTo(map).bindPopup(p.label);
  }});
  var group = L.featureGroup(markers);
  map.fitBounds(group.getBounds(), {{maxZoom: 18, padding: [20, 20]}});
}})();
</script>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        q = parse_qs(parsed.query).get("q", [None])[0]

        if parsed.path == "/uprn" and q:
            self.redirect(f"/uprn/{q.strip()}")
        elif parsed.path == "/usrn" and q:
            self.redirect(f"/usrn/{q.strip()}")
        elif parsed.path == "/postcode" and q:
            self.redirect(f"/postcode/{quote(normalize_postcode(q))}")
        elif parsed.path == "/udprn" and q:
            self.redirect_udprn(q.strip())
        elif parsed.path.startswith("/uprn/"):
            self.show_uprn(parsed.path.removeprefix("/uprn/"))
        elif parsed.path.startswith("/usrn/"):
            self.show_usrn(parsed.path.removeprefix("/usrn/"))
        elif parsed.path.startswith("/postcode/"):
            self.show_postcode(unquote(parsed.path.removeprefix("/postcode/")))
        elif parsed.path.startswith("/udprn/"):
            self.redirect_udprn(parsed.path.removeprefix("/udprn/"))
        else:
            self.respond(PAGE.format(title="AddressBase", forms=SEARCH_FORMS, body=""))

    def redirect(self, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def respond(self, body, status=200):
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def show_uprn(self, uprn):
        sections = []
        usrns = set()
        points = []
        for table in UPRN_TABLES:
            cols, rows = query_rows(self.server.con, table, "UPRN", uprn)
            if table == "classification":
                cols, rows = add_classification_descriptions(self.server.con, cols, rows)
            if table == "blpu":
                cols, rows = add_custodian_names(self.server.con, cols, rows)
            sections.append(render_table(table, cols, rows))
            if table == "lpi" and "USRN" in cols:
                usrns.update(row[cols.index("USRN")] for row in rows)
            if table == "blpu" and "LATITUDE" in cols and "LONGITUDE" in cols:
                lat_i, lon_i = cols.index("LATITUDE"), cols.index("LONGITUDE")
                points.extend((row[lat_i], row[lon_i], f"UPRN {uprn}", None) for row in rows)
        links = "".join(f'<p><a href="/usrn/{u}">USRN {u}</a></p>' for u in sorted(usrns))
        body = f"<h1>UPRN {html.escape(uprn)}</h1>{render_map(points)}{links}" + "".join(sections)
        self.respond(PAGE.format(title=f"UPRN {uprn}", forms="", body=body))

    def show_usrn(self, usrn):
        sections = []
        points = []
        for table in USRN_TABLES:
            cols, rows = query_rows(self.server.con, table, "USRN", usrn)
            sections.append(render_table(table, cols, rows))
            if table == "street" and "STREET_START_LAT" in cols:
                start_lat, start_lon = cols.index("STREET_START_LAT"), cols.index("STREET_START_LONG")
                end_lat, end_lon = cols.index("STREET_END_LAT"), cols.index("STREET_END_LONG")
                for row in rows:
                    points.append((row[start_lat], row[start_lon], f"USRN {usrn} START", "red"))
                    points.append((row[end_lat], row[end_lon], f"USRN {usrn} END", "red"))
        cols, rows = query_rows(self.server.con, "lpi", "USRN", usrn)
        uprns = sorted({row[cols.index("UPRN")] for row in rows}) if "UPRN" in cols else []
        if uprns:
            blpu_rows = self.server.con.execute(
                "SELECT UPRN, LATITUDE, LONGITUDE FROM blpu WHERE UPRN IN "
                f"({','.join('?' * len(uprns))})",
                uprns,
            ).fetchall()
            points.extend((lat, lon, f"UPRN <a href='/uprn/{uprn}'>{uprn}</a>", None) for uprn, lat, lon in blpu_rows)
        links = "".join(f'<p><a href="/uprn/{uprn}">UPRN {uprn}</a></p>' for uprn in uprns)
        body = (
            f"<h1>USRN {html.escape(usrn)}</h1>{render_map(points)}"
            + "".join(sections)
            + f"<h2>addresses on this street</h2>{links}"
        )
        self.respond(PAGE.format(title=f"USRN {usrn}", forms="", body=body))

    def show_postcode(self, postcode):
        postcode = normalize_postcode(postcode)
        con = self.server.con
        uprn_rows = con.execute(
            "SELECT UPRN, LATITUDE, LONGITUDE FROM blpu WHERE POSTCODE_LOCATOR = ? ORDER BY UPRN", [postcode]
        ).fetchall()
        uprns = [row[0] for row in uprn_rows]
        points = [(lat, lon, f"UPRN {uprn}", None) for uprn, lat, lon in uprn_rows]

        usrns = []
        if uprns:
            usrn_rows = con.execute(
                f"SELECT DISTINCT USRN FROM lpi WHERE UPRN IN ({','.join('?' * len(uprns))})", uprns
            ).fetchall()
            usrns = sorted(row[0] for row in usrn_rows if row[0] is not None)
        if usrns:
            street_rows = con.execute(
                "SELECT USRN, STREET_START_LAT, STREET_START_LONG, STREET_END_LAT, STREET_END_LONG "
                f"FROM street WHERE USRN IN ({','.join('?' * len(usrns))})",
                usrns,
            ).fetchall()
            for usrn, start_lat, start_lon, end_lat, end_lon in street_rows:
                points.append((start_lat, start_lon, f"USRN {usrn} START", "red"))
                points.append((end_lat, end_lon, f"USRN {usrn} END", "red"))

        street_table = ""
        if usrns:
            street_rows = con.execute(
                "SELECT USRN, STREET_DESCRIPTION, LOCALITY, TOWN_NAME FROM street_descriptor "
                f"WHERE USRN IN ({','.join('?' * len(usrns))}) ORDER BY USRN",
                usrns,
            ).fetchall()
            street_table = render_table(
                "streets", ["USRN", "STREET_DESCRIPTION", "LOCALITY", "TOWN_NAME"], street_rows
            )

        uprn_table = ""
        if uprns:
            sao_by_uprn = field_by_uprn(con, "lpi", uprns, SAO_FIELDS)
            pao_by_uprn = field_by_uprn(con, "lpi", uprns, PAO_FIELDS)
            address_by_uprn = field_by_uprn(con, "delivery_point_address", uprns, DELIVERY_ADDRESS_FIELDS, sep=", ")
            uprn_summary_rows = [
                (uprn, sao_by_uprn.get(uprn, ""), pao_by_uprn.get(uprn, ""), address_by_uprn.get(uprn, ""))
                for uprn in uprns
            ]
            uprn_table = render_table("addresses", ["UPRN", "SAO", "PAO", "DELIVERY_ADDRESS"], uprn_summary_rows)

        body = (
            f"<h1>postcode {html.escape(postcode)}</h1>{render_map(points)}"
            f"{street_table}"
            f"{uprn_table}"
        )
        self.respond(PAGE.format(title=f"postcode {postcode}", forms="", body=body))

    def redirect_udprn(self, udprn):
        row = self.server.con.execute(
            "SELECT UPRN FROM delivery_point_address WHERE UDPRN = ?", [udprn]
        ).fetchone()
        if row:
            self.redirect(f"/uprn/{row[0]}")
        else:
            self.respond(f"<h1>UDPRN {html.escape(udprn)}</h1><p>not found</p>", status=404)

    def log_message(self, format, *args):
        print(f"{self.address_string()} {format % args}", file=sys.stderr)


def main():
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    server.con = duckdb.connect(str(DATABASE_FILE), read_only=True)
    print(f"serving on http://localhost:{PORT}", file=sys.stderr)
    try:
        server.serve_forever()
    finally:
        server.con.close()


if __name__ == "__main__":
    main()
