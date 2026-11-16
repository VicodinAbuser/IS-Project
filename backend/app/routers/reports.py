"""Admin dashboard numbers and quarterly reports (JSON for charts, CSV/Excel for download)."""
import csv
import io

import oracledb
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font

from ..database import get_db, query, query_one
from ..security import Perm, require

router = APIRouter(prefix="/api/reports", tags=["Reports (staff)"])
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


@router.get("/dashboard")
def dashboard(db: oracledb.Connection = Depends(get_db), _: dict = Depends(require(Perm.REPORT_VIEW))):
    return query_one(db, """
        SELECT (SELECT NVL(SUM(total_amount), 0) FROM orders WHERE order_status = 'PAID')            AS total_revenue,
               (SELECT COUNT(*) FROM orders WHERE order_status = 'PAID')                             AS paid_orders,
               (SELECT COUNT(*) FROM orders WHERE order_status = 'PENDING_PAYMENT')                  AS pending_payment,
               (SELECT COUNT(*) FROM orders o JOIN deliveries d ON d.order_id = o.order_id
                 WHERE o.order_status = 'PAID' AND d.delivery_status IN ('NOT_SHIPPED', 'PACKED'))   AS to_ship,
               (SELECT COUNT(*) FROM products WHERE is_active = 1)                                   AS products,
               (SELECT COUNT(*) FROM outlets)                                                         AS outlets,
               (SELECT NVL(SUM(quantity), 0) FROM inventory)                                         AS total_units_in_stock,
               (SELECT COUNT(*) FROM v_inventory_status WHERE low_stock = 1)                         AS low_stock_items
          FROM dual""")


def build_quarterly(db: oracledb.Connection, year: int, quarter: int) -> dict:
    """Aggregates the V_SALES_LINES view (paid order lines) for one quarter."""
    start_month = 3 * (quarter - 1) + 1
    end = f"{year + 1}-01-01" if quarter == 4 else f"{year}-{start_month + 3:02d}-01"
    p = {"y": year, "q": quarter}
    in_q = "FROM v_sales_lines WHERE sales_year = :y AND sales_quarter = :q"

    summary = query_one(db, f"""SELECT COUNT(DISTINCT order_id) AS orders, NVL(SUM(quantity), 0) AS units_sold,
                                       NVL(SUM(revenue), 0) AS revenue {in_q}""", p)
    by_outlet = query(db, f"""SELECT outlet_name AS outlet, COUNT(DISTINCT order_id) AS orders,
                                     SUM(quantity) AS units, SUM(revenue) AS revenue {in_q}
                               GROUP BY outlet_name ORDER BY revenue DESC""", p)
    by_product = query(db, f"""SELECT sku, product_name AS product, SUM(quantity) AS units, SUM(revenue) AS revenue {in_q}
                                GROUP BY sku, product_name ORDER BY revenue DESC""", p)
    by_category = query(db, f"""SELECT category_name AS category, SUM(quantity) AS units, SUM(revenue) AS revenue {in_q}
                                 GROUP BY category_name ORDER BY revenue DESC""", p)
    monthly_rows = {r["sales_month"]: r["revenue"] for r in
                    query(db, f"SELECT sales_month, SUM(revenue) AS revenue {in_q} GROUP BY sales_month", p)}
    stock = query(db, """SELECT o.name AS outlet, NVL(SUM(i.quantity), 0) AS units
                           FROM outlets o LEFT JOIN inventory i ON i.outlet_id = o.outlet_id
                          GROUP BY o.name ORDER BY o.name""")
    return {
        "year": year, "quarter": quarter,
        "period": f"{year}-{start_month:02d}-01 to {end} (exclusive)",
        "summary": {"orders": summary["orders"], "units_sold": int(summary["units_sold"]),
                    "revenue": round(float(summary["revenue"]), 2)},
        "by_outlet": [{**r, "units": int(r["units"]), "revenue": round(float(r["revenue"]), 2)} for r in by_outlet],
        "by_product": [{**r, "units": int(r["units"]), "revenue": round(float(r["revenue"]), 2)} for r in by_product],
        "by_category": [{**r, "units": int(r["units"]), "revenue": round(float(r["revenue"]), 2)} for r in by_category],
        "monthly": [{"month": MONTHS[m - 1], "revenue": round(float(monthly_rows.get(m, 0)), 2)}
                    for m in range(start_month, start_month + 3)],
        "current_stock_by_outlet": [{"outlet": r["outlet"], "units": int(r["units"])} for r in stock],
    }


@router.get("/quarterly")
def quarterly(year: int = Query(..., ge=2000, le=2100), quarter: int = Query(..., ge=1, le=4),
              db: oracledb.Connection = Depends(get_db), _: dict = Depends(require(Perm.REPORT_VIEW))):
    return build_quarterly(db, year, quarter)


SECTIONS = [("By outlet", "by_outlet"), ("By product", "by_product"), ("By category", "by_category"),
            ("Monthly revenue", "monthly"), ("Current stock by outlet", "current_stock_by_outlet")]


@router.get("/quarterly/export")
def export(year: int = Query(..., ge=2000, le=2100), quarter: int = Query(..., ge=1, le=4),
           format: str = Query("xlsx", pattern="^(csv|xlsx)$"),
           db: oracledb.Connection = Depends(get_db), _: dict = Depends(require(Perm.REPORT_DOWNLOAD))):
    data = build_quarterly(db, year, quarter)
    name = f"inventory_report_{year}_Q{quarter}"

    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([f"Quarterly report {year} Q{quarter}", data["period"]])
        w.writerow(["Orders", "Units sold", "Revenue"])
        w.writerow(data["summary"].values())
        for title, key in SECTIONS:
            w.writerow([])
            w.writerow([title])
            if data[key]:
                w.writerow(data[key][0].keys())
                for row in data[key]:
                    w.writerow(row.values())
        return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                                 headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})

    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.append([f"Quarterly report {year} Q{quarter}"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([data["period"]])
    ws.append([])
    ws.append(["Orders", "Units sold", "Revenue"])
    ws.append(list(data["summary"].values()))
    for title, key in SECTIONS:
        sheet = wb.create_sheet(title[:31])
        if data[key]:
            sheet.append([h.replace("_", " ").title() for h in data[key][0].keys()])
            for c in sheet[1]:
                c.font = Font(bold=True)
            for row in data[key]:
                sheet.append(list(row.values()))
    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return StreamingResponse(out, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})
