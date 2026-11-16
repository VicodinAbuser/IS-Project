"""Sorting and "latest updated" filters shared by the list endpoints.

Each list endpoint declares which sort options it offers, e.g.
    ORDER_SORTS = {"updated_desc": "o.updated_at DESC", "amount_desc": "o.total_amount DESC", ...}
and the browser sends ?sort=updated_desc&updated_within=7. Only names from that dictionary are
accepted, so nothing the user types ever becomes part of the SQL text (no SQL injection).
"""
from fastapi import HTTPException, Query

# "Updated within" choices offered in the UI (days). 0 / missing = any time.
UPDATED_WITHIN = Query(None, ge=1, le=3650, description="Only rows changed in the last N days (1 = today)")


def order_by(sort: str | None, options: dict[str, str], default: str, tie_breaker: str) -> str:
    if sort is None:
        sort = default
    if sort not in options:
        raise HTTPException(422, f"sort must be one of: {', '.join(options)}")
    return f" ORDER BY {options[sort]}, {tie_breaker}"


def updated_within(column: str, days: int | None, where: list[str], params: dict) -> None:
    """Adds 'column changed in the last N days' to a WHERE list (1 = since midnight today)."""
    if days:
        where.append(f"{column} >= TRUNC(SYSDATE) - :within_days")
        params["within_days"] = days - 1


def where_sql(where: list[str]) -> str:
    return (" WHERE " + " AND ".join(where)) if where else ""
