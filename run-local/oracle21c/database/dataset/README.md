# Large dataset: 50,000 customers (CSV)

One CSV file per table, ready to load into the Oracle schema from `01_schema.sql`.
They cover trading from **1 Jan 2025 to 15 Nov 2026**, so every quarter in the reports has data.

| File | Rows | What it holds |
|---|---:|---|
| `app_users.csv` | 50,003 | 50,000 customers + 3 admins (`admin@`, `manager@`, `warehouse@inventory.com`) |
| `outlets.csv` | 10 | Mumbai, Pune, Bengaluru, Delhi, Chennai, Hyderabad, Kolkata, Ahmedabad, Jaipur, Kochi |
| `categories.csv` | 8 | Electronics, Stationery, Home & Kitchen, Apparel, Sports & Fitness, Beauty & Personal Care, Books, Toys & Games |
| `suppliers.csv` | 12 | |
| `products.csv` | 89 | 86 active, 3 withdrawn (`is_active = 0`). Some were added to the range during 2025–26. |
| `inventory.csv` | 890 | Current stock: one row per product per outlet. 3 rows are deliberately low, for the low-stock alert. |
| `orders.csv` | 89,260 | 80,609 PAID, 6,092 CANCELLED, 2,559 RETURNED |
| `order_items.csv` | 172,140 | 1–5 products per order |
| `payments.csv` | 89,260 | One per order: SUCCESS, REFUNDED or CANCELLED |
| `deliveries.csv` | 89,260 | One per order: NOT_SHIPPED, PACKED, SHIPPED, OUT_FOR_DELIVERY, DELIVERED or RETURNED |
| `stock_movements.csv` | 192,254 | Full stock history: RESTOCK, SALE, CANCEL, RETURN, ADJUSTMENT, TRANSFER_IN/OUT |

**Passwords:** every customer uses `customer123`, and the admins use `admin123`. The CSV holds the bcrypt hash, never the password.
The 4 demo logins from the small dataset (`customer@inventory.com`, `priya@`, `rahul@`, `aisha@example.com`) keep the same user IDs 2–5.

## Format
- UTF-8, comma-separated, first row = column names (the same names as in the table).
- Text containing commas is in double quotes, e.g. `"Flat 1203, Lotus Towers, MG Road, Powai, Mumbai - 400076"`.
- An empty value means NULL.
- Dates are `YYYY-MM-DD HH:MM:SS`, which is Oracle format `YYYY-MM-DD HH24:MI:SS`.
- Money has 2 decimals (`1299.00`).
- IDs are included, so the foreign keys between the files line up.
- Names, emails, phone numbers and addresses are made up. Emails use reserved `example` domains, so they can't belong to anyone real.

## How the data was made (and why it is consistent)
`tools/generate_dataset.py` *simulates* the shop in time order, following the same rules as `INVENTORY_PKG`:

- **Opening stock, restocks and transfers:**
  - Each product gets opening stock at every outlet when it is launched.
  - When an outlet runs low, an admin restocks it from the supplier (`PO-1234 received from …`), or transfers stock from the outlet with the most.
  - Weekly stock audits make small ADJUSTMENTs.
- **Placing an order:** stock is taken at the moment the order is placed (a SALE movement), never more than is on the shelf. `total_amount` = sum of `quantity × unit_price`.
- **Payment:** SUCCESS gets a method and a unique `TXN-…` reference. 6% of orders had a declined attempt first.
- **Delivery:** PACKED when paid → SHIPPED (courier + tracking number) → OUT_FOR_DELIVERY → DELIVERED. Recent orders are still on the way.
- **Abandoned checkouts:** not paid within 30 minutes, so the order is CANCELLED, payment CANCELLED and stock CANCELLED back (`not paid within 30 minutes`).
- **Cancelled by the customer before shipping:** stock goes back. The payment becomes REFUNDED if it was paid, CANCELLED if not.
- **Returned after delivery:** delivery RETURNED, stock RETURNED to the outlet, payment REFUNDED, order RETURNED.

`tools/validate_dataset.py` checks the CSV files independently. It covers:
- every PK, UNIQUE, NOT NULL, CHECK and FK constraint, and the column lengths;
- totals and payment amounts;
- that only status combinations the package can produce appear;
- that every order's SALE, CANCEL and RETURN movements match its items;
- that stock never goes below 0, replayed in time order, and that each inventory quantity equals the sum of its movements;
- that dates are in order: sign-up → order → payment → delivery.

```bash
python tools/validate_dataset.py
```

## Loading it into Oracle

**Easiest:** in the `run-local` folder, double-click `6-load-big-dataset.bat`. By hand, run this inside `backend`:

```bash
python load_dataset.py
```

It runs in 2–5 minutes and does these steps in order:
1. Empties the tables.
2. Turns the audit trigger off while loading, because the history is already in `stock_movements.csv`.
3. Inserts the files, parents first.
4. Turns the trigger back on and moves the identity counters past the loaded IDs, so the next order gets the next number.
5. Runs checks inside Oracle.

To go back to the small demo data, run `5-reset-demo-data.bat` (or `python setup_db.py`).

**In SQL Developer instead** (slower, one table at a time): right-click a table → **Import Data…**, choose the CSV, tick **Header**, and set the date format to `YYYY-MM-DD HH24:MI:SS`. Do these first:
1. Empty the tables.
2. Run `ALTER TRIGGER trg_inventory_audit DISABLE;`.
3. Import in this order: app_users, outlets, categories, suppliers, products, inventory, orders, order_items, payments, deliveries, stock_movements.

Afterwards, enable the trigger again. Then, for each table, run `ALTER TABLE orders MODIFY order_id GENERATED BY DEFAULT AS IDENTITY (START WITH LIMIT VALUE);`, changing the table and ID column names each time.

## Queries to show in SQL Developer
```sql
SELECT user_role, COUNT(*) FROM app_users GROUP BY user_role;

SELECT order_status, COUNT(*), SUM(total_amount) FROM orders GROUP BY order_status;

-- revenue per quarter (same view the reports use)
SELECT sales_year, sales_quarter, SUM(revenue) AS revenue, COUNT(DISTINCT order_id) AS orders
  FROM v_sales_lines GROUP BY sales_year, sales_quarter ORDER BY 1, 2;

-- top 10 customers by spend
SELECT u.full_name, u.email, COUNT(*) AS orders, SUM(o.total_amount) AS spent
  FROM orders o JOIN app_users u ON u.user_id = o.customer_id
 WHERE o.order_status = 'PAID'
 GROUP BY u.full_name, u.email ORDER BY spent DESC FETCH FIRST 10 ROWS ONLY;

-- proof the stock history is complete: should return no rows
SELECT i.product_id, i.outlet_id, i.quantity, SUM(m.qty_change) AS from_history
  FROM inventory i JOIN stock_movements m ON m.product_id = i.product_id AND m.outlet_id = i.outlet_id
 GROUP BY i.product_id, i.outlet_id, i.quantity HAVING i.quantity <> SUM(m.qty_change);
```

To regenerate the files (same seed, same result), run `python tools/generate_dataset.py`.
