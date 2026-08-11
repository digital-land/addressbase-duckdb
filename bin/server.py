#!/usr/bin/env python3

# Simple web viewer over the duckdb database: look up every row related to a
# UPRN or a USRN across all tables, cross-linked via the LPI table (which
# maps UPRN to USRN).

import html
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import duckdb

DATABASE_FILE = Path("database/addressbase.duckdb")
PORT = 8000

UPRN_TABLES = ["blpu", "lpi", "classification", "delivery_point_address", "organisation", "xref", "successor"]
USRN_TABLES = ["street", "street_descriptor"]

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>
body {{ font-family: sans-serif; margin: 2em; }}
table {{ border-collapse: collapse; margin-bottom: 2em; }}
th, td {{ border: 1px solid #ccc; padding: 4px 8px; font-size: 0.85em; }}
th {{ background: #eee; text-align: left; }}
form {{ margin-bottom: 0.5em; }}
input {{ font-size: 1em; padding: 4px; }}
</style></head>
<body>
<h1><a href="/">AddressBase</a></h1>
<form action="/uprn" method="get"><label>UPRN <input name="q" autofocus></label> <button>search</button></form>
<form action="/usrn" method="get"><label>USRN <input name="q"></label> <button>search</button></form>
{body}
</body></html>
"""


def query_rows(con, table, column, value):
    cols = [row[0] for row in con.execute(f"DESCRIBE {table}").fetchall()]
    if column not in cols:
        return cols, []
    rows = con.execute(f"SELECT * FROM {table} WHERE CAST({column} AS VARCHAR) = ?", [value]).fetchall()
    return cols, rows


def render_table(name, cols, rows):
    if not rows:
        return ""
    head = "".join(f"<th>{html.escape(c)}</th>" for c in cols)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(v)) if v is not None else ''}</td>" for v in row) + "</tr>"
        for row in rows
    )
    return f"<h2>{html.escape(name)}</h2><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        q = parse_qs(parsed.query).get("q", [None])[0]

        if parsed.path == "/uprn" and q:
            self.redirect(f"/uprn/{q.strip()}")
        elif parsed.path == "/usrn" and q:
            self.redirect(f"/usrn/{q.strip()}")
        elif parsed.path.startswith("/uprn/"):
            self.show_uprn(parsed.path.removeprefix("/uprn/"))
        elif parsed.path.startswith("/usrn/"):
            self.show_usrn(parsed.path.removeprefix("/usrn/"))
        else:
            self.respond(PAGE.format(title="AddressBase", body=""))

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
        for table in UPRN_TABLES:
            cols, rows = query_rows(self.server.con, table, "UPRN", uprn)
            sections.append(render_table(table, cols, rows))
            if table == "lpi" and "USRN" in cols:
                usrns.update(row[cols.index("USRN")] for row in rows)
        links = "".join(f'<p><a href="/usrn/{u}">street USRN {u}</a></p>' for u in sorted(usrns))
        body = f"<h1>UPRN {html.escape(uprn)}</h1>{links}" + "".join(sections)
        self.respond(PAGE.format(title=f"UPRN {uprn}", body=body))

    def show_usrn(self, usrn):
        sections = [render_table(table, *query_rows(self.server.con, table, "USRN", usrn)) for table in USRN_TABLES]
        cols, rows = query_rows(self.server.con, "lpi", "USRN", usrn)
        uprns = sorted({row[cols.index("UPRN")] for row in rows}) if "UPRN" in cols else []
        links = "".join(f'<p><a href="/uprn/{u}">UPRN {u}</a></p>' for u in uprns)
        body = f"<h1>USRN {html.escape(usrn)}</h1>" + "".join(sections) + f"<h2>addresses on this street</h2>{links}"
        self.respond(PAGE.format(title=f"USRN {usrn}", body=body))

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
