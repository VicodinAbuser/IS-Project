"""Admin dashboard numbers and quarterly reports (JSON for charts, CSV/Excel for download)."""
import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (Category, Delivery, DeliveryStatus, Inventory, Order, OrderItem, OrderStatus,
                      Outlet, Product, User)
from ..security import require_admin

router = APIRouter(prefix="/api/reports", tags=["Reports (admin)"])


def quarter_range(year: int, quarter: int) -> tuple[datetime, datetime]:
    start = datetime(year, 3 * (quarter - 1) + 1, 1, tzinfo=timezone.utc)
    end = datetime(year + 1, 1, 1, tzinfo=timezone.utc) if quarter == 4 else \
        datetime(year, 3 * quarter + 1, 1, tzinfo=timezone.utc)
    return start, end


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    paid = Order.status == OrderStatus.PAID
    low = db.scalar(select(func.count()).select_from(Inventory).join(Product)
                    .where(Inventory.quantity <= Product.reorder_level, Product.is_active.is_(True)))
    return {
        "total_revenue": round(float(db.scalar(select(func.coalesce(func.sum(Order.total_amount), 0)).where(paid))), 2),
        "paid_orders": db.scalar(select(func.count()).select_from(Order).where(paid)),
        "pending_payment": db.scalar(select(func.count()).select_from(Order)
                                     .where(Order.status == OrderStatus.PENDING_PAYMENT)),
        "to_ship": db.scalar(select(func.count()).select_from(Order).join(Delivery)
                             .where(paid, Delivery.status.in_([DeliveryStatus.PACKED, DeliveryStatus.NOT_SHIPPED]))),
        "products": db.scalar(select(func.count()).select_from(Product).where(Product.is_active.is_(True))),
        "outlets": db.scalar(select(func.count()).select_from(Outlet)),
        "total_units_in_stock": int(db.scalar(select(func.coalesce(func.sum(Inventory.quantity), 0)))),
        "low_stock_items": low,
    }


def build_quarterly(db: Session, year: int, quarter: int) -> dict:
    start, end = quarter_range(year, quarter)
    in_q = (Order.status == OrderStatus.PAID, Order.created_at >= start, Order.created_at < end)
    revenue = OrderItem.quantity * OrderItem.unit_price

    summary = db.execute(select(func.count(func.distinct(Order.id)),
                                func.coalesce(func.sum(OrderItem.quantity), 0),
                                func.coalesce(func.sum(revenue), 0))
                         .select_from(Order).join(OrderItem).where(*in_q)).one()

    by_outlet = db.execute(select(Outlet.name, func.count(func.distinct(Order.id)),
                                  func.sum(OrderItem.quantity), func.sum(revenue))
                           .select_from(Order).join(OrderItem).join(Outlet)
                           .where(*in_q).group_by(Outlet.name).order_by(func.sum(revenue).desc())).all()

    by_product = db.execute(select(Product.sku, Product.name, func.sum(OrderItem.quantity), func.sum(revenue))
                            .select_from(Order).join(OrderItem).join(Product)
                            .where(*in_q).group_by(Product.id).order_by(func.sum(revenue).desc())).all()

    by_category = db.execute(select(func.coalesce(Category.name, "Uncategorised"), func.sum(OrderItem.quantity),
                                    func.sum(revenue))
                             .select_from(Order).join(OrderItem).join(Product)
                             .outerjoin(Category, Category.id == Product.category_id)
                             .where(*in_q).group_by(Category.name).order_by(func.sum(revenue).desc())).all()

    # Monthly breakdown done in Python so it works the same on SQLite and PostgreSQL.
    months = {start.month + i: 0.0 for i in range(3)}
    for created, amount in db.execute(select(Order.created_at, Order.total_amount).where(*in_q)).all():
        months[created.month] = months.get(created.month, 0.0) + float(amount)

    stock = db.execute(select(Outlet.name, func.coalesce(func.sum(Inventory.quantity), 0))
                       .outerjoin(Inventory, Inventory.outlet_id == Outlet.id)
                       .group_by(Outlet.name).order_by(Outlet.name)).all()

    return {
        "year": year, "quarter": quarter,
        "period": f"{start.date()} to {end.date()} (exclusive)",
        "summary": {"orders": summary[0], "units_sold": int(summary[1]), "revenue": round(float(summary[2]), 2)},
        "by_outlet": [{"outlet": n, "orders": o, "units": int(u), "revenue": round(float(r), 2)}
                      for n, o, u, r in by_outlet],
        "by_product": [{"sku": s, "product": n, "units": int(u), "revenue": round(float(r), 2)}
                       for s, n, u, r in by_product],
        "by_category": [{"category": c, "units": int(u), "revenue": round(float(r), 2)}
                        for c, u, r in by_category],
        "monthly": [{"month": datetime(year, m, 1).strftime("%b"), "revenue": round(v, 2)}
                    for m, v in sorted(months.items())],
        "current_stock_by_outlet": [{"outlet": n, "units": int(q)} for n, q in stock],
    }



@router.get("/quarterly")
def quarterly(year: int = Query(..., ge=2000, le=2100), quarter: int = Query(..., ge=1, le=4),
              db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return build_quarterly(db, year, quarter)


SECTIONS = [("By outlet", "by_outlet"), ("By product", "by_product"), ("By category", "by_category"),
            ("Monthly revenue", "monthly"), ("Current stock by outlet", "current_stock_by_outlet")]


@router.get("/quarterly/export")
def export(year: int = Query(..., ge=2000, le=2100), quarter: int = Query(..., ge=1, le=4),
           format: str = Query("xlsx", pattern="^(csv|xlsx)$"),
           db: Session = Depends(get_db), _: User = Depends(require_admin)):
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
