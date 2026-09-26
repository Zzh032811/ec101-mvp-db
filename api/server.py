"""Cross-platform, read-only HTTP API for the EC101 SQLite business facts."""

from __future__ import annotations

import argparse
import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "mvp" / "ec101_mvp.db"


def _config(select: str, joins: str, search: tuple[str, ...], id_column: str, order: str):
    return {"select": select, "joins": joins, "search": search, "id_column": id_column, "order": order}


CONFIGS = {
    "orders": _config(
        "oh.order_id AS id, oh.order_no, dp.dealer_name AS dealer, dp.platform_name AS platform, c.customer_name AS customer, oh.order_time, oh.order_status, oh.batch_id AS source_batch",
        "JOIN dealer_platform dp ON dp.dealer_platform_id = oh.dealer_platform_id LEFT JOIN customer c ON c.customer_id = oh.customer_id",
        ("oh.order_no", "c.customer_name", "oh.order_status"),
        "oh.order_id",
        "oh.order_id",
    ),
    "order-lines": _config(
        "ol.order_line_id AS id, oh.order_no, dp.dealer_name AS dealer, dp.platform_name AS platform, p.product_name AS product, p.platform_product_no AS product_no, ol.order_qty, ol.order_unit, ol.pre_discount_amount, ol.discount_amount",
        "JOIN order_header oh ON oh.order_id = ol.order_id JOIN dealer_platform dp ON dp.dealer_platform_id = oh.dealer_platform_id LEFT JOIN product p ON p.product_id = ol.product_id",
        ("oh.order_no", "p.product_name", "p.platform_product_no"),
        "ol.order_line_id",
        "ol.order_line_id",
    ),
    "activities": _config(
        "a.activity_id AS id, a.activity_name, dp.dealer_name AS dealer, dp.platform_name AS platform, a.promotion_type, a.start_time, a.end_time, a.activity_status, a.rule_version",
        "JOIN dealer_platform dp ON dp.dealer_platform_id = a.dealer_platform_id",
        ("a.activity_name", "a.promotion_type", "a.activity_status"),
        "a.activity_id",
        "a.activity_id",
    ),
    "activity-details": _config(
        "oa.order_activity_id AS id, oh.order_no, dp.dealer_name AS dealer, dp.platform_name AS platform, a.activity_name, oa.activity_product_amount, oa.platform_actual_benefit, oa.gift_qty_actual, oa.exec_status, oa.evidence_ref",
        "JOIN order_header oh ON oh.order_id = oa.order_id JOIN dealer_platform dp ON dp.dealer_platform_id = oh.dealer_platform_id JOIN activity a ON a.activity_id = oa.activity_id",
        ("oh.order_no", "a.activity_name", "oa.exec_status"),
        "oa.order_activity_id",
        "oa.order_activity_id",
    ),
    "customers": _config(
        "c.customer_id AS id, c.platform_customer_no AS customer_no, dp.dealer_name AS dealer, dp.platform_name AS platform, c.customer_name, c.customer_type, c.customer_level, c.customer_region, c.salesperson_name, c.status",
        "JOIN dealer_platform dp ON dp.dealer_platform_id = c.dealer_platform_id",
        ("c.platform_customer_no", "c.customer_name", "c.customer_region", "c.salesperson_name"),
        "c.customer_id",
        "c.customer_id",
    ),
    "products": _config(
        "p.product_id AS id, p.platform_product_no AS product_no, dp.dealer_name AS dealer, dp.platform_name AS platform, p.product_name, p.brand, p.category, p.spec, p.base_unit, p.shelf_status",
        "JOIN dealer_platform dp ON dp.dealer_platform_id = p.dealer_platform_id",
        ("p.platform_product_no", "p.product_name", "p.brand", "p.category"),
        "p.product_id",
        "p.product_id",
    ),
    "fulfillments": _config(
        "f.fulfillment_id AS id, oh.order_no, dp.dealer_name AS dealer, dp.platform_name AS platform, f.order_status, f.completed_at, f.t2_release_candidate, f.return_qty, f.special_reason",
        "JOIN order_header oh ON oh.order_id = f.order_id JOIN dealer_platform dp ON dp.dealer_platform_id = oh.dealer_platform_id",
        ("oh.order_no", "f.order_status", "f.special_reason"),
        "f.fulfillment_id",
        "f.fulfillment_id",
    ),
    "order-activities": _config(
        "oa.order_activity_id AS id, oh.order_no, dp.dealer_name AS dealer, dp.platform_name AS platform, a.activity_name, ar.threshold_value, ar.reduce_amount, oa.activity_product_amount, oa.platform_actual_benefit, oa.exec_status",
        "JOIN order_header oh ON oh.order_id = oa.order_id JOIN dealer_platform dp ON dp.dealer_platform_id = oh.dealer_platform_id JOIN activity a ON a.activity_id = oa.activity_id LEFT JOIN activity_rule ar ON ar.rule_id = oa.rule_id",
        ("oh.order_no", "a.activity_name", "oa.exec_status"),
        "oa.order_activity_id",
        "oa.order_activity_id",
    ),
}
SUPPORTED_OBJECTS = tuple(CONFIGS)


def _conditions(config: dict[str, Any], params: dict[str, Any]) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    values: list[Any] = []
    dealer = str(params.get("dealer", "")).strip()
    platform = str(params.get("platform", "")).strip()
    search = str(params.get("q", "")).strip()
    if dealer:
        clauses.append("dp.dealer_name LIKE ?")
        values.append(f"%{dealer}%")
    if platform:
        clauses.append("dp.platform_name LIKE ?")
        values.append(f"%{platform}%")
    if search:
        clauses.append("(" + " OR ".join(f"{column} LIKE ?" for column in config["search"]) + ")")
        values.extend([f"%{search}%"] * len(config["search"]))
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", values


def _bounds(params: dict[str, Any]) -> tuple[int, int]:
    try:
        limit = min(max(int(params.get("limit", 50)), 1), 100)
        offset = min(max(int(params.get("offset", 0)), 0), 10000)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit and offset must be integers") from exc
    return limit, offset


def query_dataset(db_path: Path, object_name: str, params: dict[str, Any]) -> dict[str, Any]:
    if object_name not in CONFIGS:
        raise KeyError(object_name)
    config = CONFIGS[object_name]
    where, values = _conditions(config, params)
    limit, offset = _bounds(params)
    base = f"SELECT {config['select']} FROM { {'orders':'order_header oh','order-lines':'order_line ol','activities':'activity a','activity-details':'order_activity oa','customers':'customer c','products':'product p','fulfillments':'fulfillment f','order-activities':'order_activity oa'}[object_name] } {config['joins']}"
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        total = connection.execute(f"SELECT COUNT(*) FROM ({base}{where})", values).fetchone()[0]
        rows = [dict(row) for row in connection.execute(f"{base}{where} ORDER BY {config['order']} LIMIT ? OFFSET ?", [*values, limit, offset]).fetchall()]
    return {"object": object_name, "columns": list(rows[0].keys()) if rows else [], "rows": rows, "total": total, "limit": limit, "offset": offset}


def get_detail(db_path: Path, object_name: str, record_id: str) -> dict[str, Any] | None:
    if object_name not in CONFIGS:
        raise KeyError(object_name)
    config = CONFIGS[object_name]
    bases = {"orders":"order_header oh", "order-lines":"order_line ol", "activities":"activity a", "activity-details":"order_activity oa", "customers":"customer c", "products":"product p", "fulfillments":"fulfillment f", "order-activities":"order_activity oa"}
    base = f"SELECT {config['select']} FROM {bases[object_name]} {config['joins']} WHERE {config['id_column']} = ?"
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(base, (record_id,)).fetchone()
    return dict(row) if row else None


def _cors_origin(handler: BaseHTTPRequestHandler) -> str:
    origin = handler.headers.get("Origin", "")
    return origin if origin.startswith(("http://localhost:", "http://127.0.0.1:")) else "null"


def _json(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", _cors_origin(handler))
    handler.end_headers()
    handler.wfile.write(body)


def make_handler(db_path: Path):
    class Handler(BaseHTTPRequestHandler):
        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", _cors_origin(self))
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_GET(self):
            parsed = urlparse(self.path)
            parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
            try:
                if parts == ["health"]:
                    _json(self, 200, {"status": "ok", "database": str(db_path), "objects": list(SUPPORTED_OBJECTS), "read_only": True})
                    return
                if len(parts) >= 3 and parts[:2] == ["api", "business-data"]:
                    object_name = parts[2]
                    if len(parts) == 4:
                        detail = get_detail(db_path, object_name, parts[3])
                        if detail is None:
                            _json(self, 404, {"error": "not_found"})
                        else:
                            _json(self, 200, detail)
                        return
                    query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
                    _json(self, 200, query_dataset(db_path, object_name, query))
                    return
                _json(self, 404, {"error": "not_found"})
            except KeyError:
                _json(self, 404, {"error": "unsupported_object", "objects": list(SUPPORTED_OBJECTS)})
            except ValueError as exc:
                _json(self, 400, {"error": "invalid_query", "message": str(exc)})
            except sqlite3.Error as exc:
                _json(self, 500, {"error": "database_error", "message": str(exc)})

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8787, db_path: Path = DEFAULT_DB_PATH) -> None:
    server = ThreadingHTTPServer((host, port), make_handler(db_path))
    print(f"EC101 read-only API: http://{host}:{port} (database: {db_path})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EC101 local read-only API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    args = parser.parse_args()
    serve(args.host, args.port, args.db)
