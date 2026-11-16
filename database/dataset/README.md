# Large dataset: 50,000 customers (CSV)

One CSV file per table, ready to load into the Oracle schema from `01_schema.sql`.
They cover trading from **1 Jan 2025 to 15 Nov 2026**, so every quarter in the reports has data.

| File | Rows | What it holds |
|---|---:|---|
| `users.csv` | 50,003 | Login accounts: 50,000 customers + 3 staff (`admin@`, `manager@`, `warehouse@inventory.com`), last login, status |
| `outlets.csv` | 10 | Mumbai, Pune, Bengaluru, Delhi, Chennai, Hyderabad, Kolkata, Ahmedabad, Jaipur, Kochi |
| `customer_profiles.csv` | 50,000 | One per customer: phone, address, city, state, 6-digit PIN code, nearest outlet |
| `profiles.csv` | 4 | ADMIN, STORE_MANAGER, WAREHOUSE_STAFF, CUSTOMER |
| `permissions.csv` | 12 | Rights such as STOCK_WRITE, REPORT_DOWNLOAD, with module and access type (READ / WRITE / REPORT / DOWNLOAD / ADMIN) |
| `authorizations.csv` | 29 | The authorization matrix: which profile has which permission |
| `user_profiles.csv` | 50,003 | Which user has which profile (one each in this data) |
| `categories.csv` | 8 | Electronics, Stationery, Home & Kitchen, Apparel, Sports & Fitness, Beauty & Personal Care, Books, Toys & Games |
| `suppliers.csv` | 12 | |
| `products.csv` | 89 | 86 active, 3 withdrawn (`is_active = 0`). Some were added to the range during 2025–26. |
| `inventory.csv` | 890 | Current stock: one row per product per outlet. 3 rows are deliberately low, for the low-stock alert. |
| `orders.csv` | 89,260 | 80,609 PAID, 6,092 CANCELLED, 2,559 RETURNED; `updated_at` = last change to the order, payment or delivery |
| `order_items.csv` | 172,140 | 1–5 products per order |
| `payments.csv` | 89,260 | One per order: SUCCESS, REFUNDED or CANCELLED |
| `deliveries.csv` | 89,260 | One per order: NOT_SHIPPED, PACKED, SHIPPED, OUT_FOR_DELIVERY, DELIVERED or RETURNED |
| `stock_movements.csv` | 192,254 | Full stock history: RESTOCK, SALE, CANCEL, RETURN, ADJUSTMENT, TRANSFER_IN/OUT, with the user who made each change |

**Passwords:** every customer uses `customer123`, and the three staff accounts use `admin123`. The CSV holds the bcrypt hash, never the password.
The 4 demo logins from the small dataset (`customer@inventory.com`, `priya@`, `rahul@`, `aisha@example.com`) keep the same user IDs 2–5.

## Format
- UTF-8, comma-separated, first row = column names (the same names as in the table).
- Text containing commas is in double quotes, e.g. `"Flat 1203, Lotus Towers, MG Road, Powai"`.
- An empty value means NULL.
- Dates are `YYYY-MM-DD HH:MM:SS`, which is Oracle format `YYYY-MM-DD HH24:MI:SS`.
- Money has 2 decimals (`1299.00`).
- IDs are included, so the foreign keys between the files line up.
- Names, emails, phone numbers and addresses are made up. Emails use reserved `example` domains, so they can't belong to anyone real.

## How the data was made (and why it is consistent)
`tools/generate_dataset.py` *simulates* the shop in time order, following the same business rules as the application (`backend/app/services`):

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
3. Import in this order (parents first): users, outlets, customer_profiles, profiles, permissions, authorizations, user_profiles, categories, suppliers, products, inventory, orders, order_items, payments, deliveries, stock_movements.

Afterwards, enable the trigger again. Then, for each table with an ID column, run `ALTER TABLE orders MODIFY order_id GENERATED BY DEFAULT AS IDENTITY (START WITH LIMIT VALUE);`, changing the table and ID column names each time.

## Queries to show in SQL Developer
```sql
-- users per profile
SELECT profile_name, COUNT(*) FROM user_profiles up JOIN profiles p ON p.profile_id = up.profile_id GROUP BY profile_name;

-- what each profile may do (the authorization matrix)
SELECT * FROM v_profile_permissions ORDER BY profile_code, module;

SELECT order_status, COUNT(*), SUM(total_amount) FROM orders GROUP BY order_status;

-- revenue per quarter (same view the reports use)
SELECT sales_year, sales_quarter, SUM(revenue) AS revenue, COUNT(DISTINCT order_id) AS orders
  FROM v_sales_lines GROUP BY sales_year, sales_quarter ORDER BY 1, 2;

-- top 10 customers by spend, with their city
SELECT customer_name, email, city, paid_orders, total_spent
  FROM v_customer_details ORDER BY total_spent DESC FETCH FIRST 10 ROWS ONLY;

-- the latest updated orders, with names instead of IDs
SELECT order_id, last_updated, customer_name, outlet_name, order_status, payment_status, delivery_status
  FROM v_order_details ORDER BY last_updated DESC FETCH FIRST 10 ROWS ONLY;

-- proof the stock history is complete: should return no rows
SELECT i.product_id, i.outlet_id, i.quantity, SUM(m.qty_change) AS from_history
  FROM inventory i JOIN stock_movements m ON m.product_id = i.product_id AND m.outlet_id = i.outlet_id
 GROUP BY i.product_id, i.outlet_id, i.quantity HAVING i.quantity <> SUM(m.qty_change);
```

To regenerate the files (same seed, same result), run `python tools/generate_dataset.py`.
