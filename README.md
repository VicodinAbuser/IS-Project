# StockSmart: Inventory Management System

An Information Systems course project built as a **3-tier web application**.

| Tier | Technology | Folder |
|---|---|---|
| Presentation (UI) | Angular 19 (TypeScript, SCSS, Chart.js) | `frontend/` |
| Application / business logic | Python FastAPI (REST API, JWT security) | `backend/app/` |
| Data | SQL database through SQLAlchemy ORM: SQLite for the demo, PostgreSQL in production | `backend/inventory.db` |

```mermaid
flowchart LR
  B[Browser<br/>Angular UI :4200] -- "HTTP + JSON<br/>Authorization: Bearer JWT" --> A[FastAPI backend :8000<br/>routers → business rules → ORM]
  A -- "SQL via SQLAlchemy" --> D[(SQLite / PostgreSQL)]
```

## Features

**Customer**
- Register and log in
- Pick an outlet, browse products with live stock, search and filter by category
- Add to cart and place an order. Stock is reserved straight away, so it can't be oversold.
- Payment gateway (card, UPI or net banking) with success and decline handling, plus retry
- Track orders (Packed → Shipped → Out for delivery → Delivered) and cancel before shipping, which returns the stock

**Admin**
- Dashboard: revenue, orders waiting to ship, pending payments, low-stock alerts
- Inventory: stock **per outlet**, **collective** totals across all outlets, stock value
- Update stock: **restock** (new arrival), **adjust** (damage or audit), **transfer** between outlets
- Stock movement log: every stock change is recorded with who made it, when and why
- Products: create, edit, hide (soft delete), with category, supplier and reorder level
- Orders: filter by payment, delivery status or outlet; update delivery status, courier and tracking number; cancel
- **Quarterly reports** with charts (by outlet, month, category, product), **downloadable as Excel or CSV**

## How to run

You need **Python 3.10+** and **Node.js 18+**.

### 1. Backend (port 8000)
```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate     Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
python seed.py            # creates the database with demo data (use --reset to start over)
uvicorn app.main:app --reload
```
Interactive API docs (good for the demo): http://localhost:8000/docs

### 2. Frontend (port 4200), in a second terminal
```bash
cd frontend
npm install
npm start
```
Open http://localhost:4200

| Demo login | Email | Password |
|---|---|---|
| Admin | admin@inventory.com | admin123 |
| Customer | customer@inventory.com | customer123 |

Payment test rule: a card ending in `0000`, or a UPI ID starting with `fail`, is **declined**. Anything else succeeds.

### Tests
```bash
cd backend && pytest -q        # API tests: security, purchase flow, cancel, transfer, reports
cd frontend && npm test        # Angular unit tests (*.spec.ts)
```

### Switch to PostgreSQL (optional)
Create `backend/.env` containing:
```
DATABASE_URL=postgresql+psycopg2://postgres:password@localhost:5432/inventory
```
Then run `python seed.py` again. No code changes are needed, because the ORM generates the right SQL for each database.

## Data model (ER diagram)

```mermaid
erDiagram
  USERS ||--o{ ORDERS : places
  OUTLETS ||--o{ ORDERS : fulfils
  OUTLETS ||--o{ INVENTORY : holds
  PRODUCTS ||--o{ INVENTORY : "stocked as"
  CATEGORIES ||--o{ PRODUCTS : groups
  SUPPLIERS ||--o{ PRODUCTS : supplies
  ORDERS ||--|{ ORDER_ITEMS : contains
  PRODUCTS ||--o{ ORDER_ITEMS : "sold in"
  ORDERS ||--|| PAYMENTS : "paid by"
  ORDERS ||--|| DELIVERIES : "shipped by"
  PRODUCTS ||--o{ STOCK_MOVEMENTS : logs
  OUTLETS ||--o{ STOCK_MOVEMENTS : logs

  USERS { int id PK; string email UK; string password_hash; enum role "ADMIN|CUSTOMER" }
  OUTLETS { int id PK; string name UK; string city }
  PRODUCTS { int id PK; string sku UK; string name; decimal price; int reorder_level; bool is_active; int category_id FK; int supplier_id FK }
  INVENTORY { int id PK; int product_id FK; int outlet_id FK; int quantity "CHECK >= 0, UNIQUE(product,outlet)" }
  STOCK_MOVEMENTS { int id PK; int change; enum movement_type; int order_id FK; int user_id FK; datetime created_at }
  ORDERS { int id PK; int customer_id FK; int outlet_id FK; enum status; decimal total_amount; datetime created_at }
  ORDER_ITEMS { int id PK; int order_id FK; int product_id FK; int quantity; decimal unit_price }
  PAYMENTS { int id PK; int order_id FK "UNIQUE"; enum status; string method; string transaction_ref }
  DELIVERIES { int id PK; int order_id FK "UNIQUE"; enum status; string courier; string tracking_number }
  CATEGORIES { int id PK; string name UK }
  SUPPLIERS { int id PK; string name UK }
```

Design decisions worth explaining:
- **`inventory` is a junction table** between products and outlets, which gives one stock row per product per outlet. Collective stock is just `SUM(quantity) GROUP BY product`.
- **`stock_movements` is an audit log.** Every stock change goes through one function (`inventory_service.change_stock`), so the stock level and its history can't drift apart.
- **`order_items.unit_price`** stores the price *at the time of purchase*, so later price changes don't rewrite old reports.
- **Constraints in the database**: `quantity >= 0`, `price >= 0`, unique SKU and email, and foreign keys. Even buggy code can't save invalid data.
- **Indexes** on `orders(created_at, status)`, `sku`, `email` and `stock_movements.created_at` keep reports and lookups fast.
- **Normalised to 3NF**: no repeated product or outlet data inside orders.

## REST API (backend ↔ UI contract)

| Method | Endpoint | Who | Purpose |
|---|---|---|---|
| POST | `/api/auth/register`, `/api/auth/login` | public | Returns a JWT and the user |
| GET | `/api/products?search=&category_id=&outlet_id=` | logged in | Catalogue with stock |
| POST/PUT/DELETE | `/api/products[/id]` | admin | Manage products |
| GET | `/api/outlets`, `/api/categories` | public | Lookups |
| GET | `/api/inventory?outlet_id=` | admin | Stock per outlet |
| GET | `/api/inventory/summary` | admin | Collective stock across outlets |
| GET | `/api/inventory/low-stock` | admin | Items at or below reorder level |
| POST | `/api/inventory/restock` · `/adjust` · `/transfer` | admin | Update stock |
| GET | `/api/inventory/movements` | admin | Audit log |
| POST | `/api/orders` | customer | Place order (reserves stock) |
| GET | `/api/orders/my` · `/api/orders` | customer · admin | List orders |
| POST | `/api/orders/{id}/pay` | owner | Payment gateway |
| POST | `/api/orders/{id}/cancel` | owner/admin | Cancel, return stock, refund |
| PATCH | `/api/orders/{id}/delivery` | admin | Delivery status and tracking |
| GET | `/api/reports/dashboard` | admin | KPI numbers |
| GET | `/api/reports/quarterly?year=&quarter=` | admin | Report JSON for charts |
| GET | `/api/reports/quarterly/export?format=xlsx\|csv` | admin | Download the report |

## Project structure

```
backend/
  app/main.py              FastAPI app, CORS, router registration
  app/config.py            settings (DB URL, JWT secret), overridable with .env
  app/database.py          engine + session per request (DB connection)
  app/models.py            tables (ORM classes)
  app/schemas.py           request/response validation (Pydantic)
  app/security.py          bcrypt hashing, JWT creation/verification, admin check
  app/inventory_service.py core stock rule: change stock + write audit log
  app/routers/             auth, catalog, inventory, orders, reports endpoints
  seed.py                  demo data (13 products, 4 outlets, ~260 orders over two years)
  tests/test_api.py        automated API tests
frontend/src/
  index.html, styles.scss  page shell + global design system
  environments/            API base URL
  app/app.routes.ts        URL → page mapping, guarded by role
  app/core/                api.service (all HTTP calls), auth.service, cart.service,
                           auth.interceptor (adds JWT), guards, models (TS interfaces)
  app/components/navbar/   role-aware navigation
  app/pages/               login, register, shop, cart, checkout, my-orders
  app/pages/admin/         dashboard, products, inventory, orders, reports
  (each component = .ts logic + .html template + .scss styles + .spec.ts test)
```

## Viva / Q&A preparation

**How is the database connected to the backend?**
`database.py` creates a SQLAlchemy *engine* from `DATABASE_URL`. Each API request gets its own *session* through FastAPI's dependency injection (`Depends(get_db)`), and the session is closed after the response. The models in `models.py` map Python classes to tables, and the ORM turns queries into SQL and uses parameter binding, which prevents SQL injection.

**How does the UI sync with the backend?**
Angular components call `ApiService`, which uses `HttpClient` to send JSON over HTTP to the REST endpoints. `authInterceptor` adds the `Authorization: Bearer <JWT>` header to every request. Responses are typed with the interfaces in `models.ts`, which mirror the backend's Pydantic schemas. After any change, such as a restock, the component fetches the data again, so the screen always shows what's in the database. CORS in `main.py` allows the UI's origin (port 4200) to call the API (port 8000).

**How is the UI developed?**
It uses standalone Angular components. Each page has a `.ts` class (state held in *signals*, plus event handlers), an `.html` template (Angular control flow `@if`/`@for`, data binding), an `.scss` file for styles and a `.spec.ts` test. Routing in `app.routes.ts` uses *guards* to block customers from admin pages. Forms use Reactive Forms with validators, and charts use Chart.js.

**What security is implemented?**
- Passwords are hashed with **bcrypt** and never stored as plain text.
- Login returns a signed **JWT** that expires after 2 hours.
- **Role-based access control**: `require_admin` blocks customers from admin APIs with HTTP 403, and customers can only see their own orders.
- Public sign-up can only create customers.
- All input is validated by Pydantic, and the database adds its own CHECK and UNIQUE constraints.
- The ORM uses parameterised queries, which blocks SQL injection.
- Route guards on the UI are for convenience only. The real enforcement happens on the server.

**How do you prevent overselling?**
Placing an order deducts stock inside a **database transaction**. If any item doesn't have enough stock, the whole order is rolled back (all or nothing). On PostgreSQL, `SELECT … FOR UPDATE` locks the stock row, so two people buying at the same moment can't both take the last unit. The `quantity >= 0` constraint is a final safety net.

**What happens when stock changes?**

| Event | Stock change | Movement type |
|---|---|---|
| New stock arrives | + | RESTOCK |
| Customer orders | − | SALE |
| Order cancelled | + | CANCEL |
| Damage or audit | ± | ADJUSTMENT |
| Moved between outlets | − / + | TRANSFER_OUT / TRANSFER_IN |

**How are quarterly reports made?**
The backend runs `GROUP BY` aggregate queries (`SUM`, `COUNT`) on paid orders between the quarter's start and end dates. The results go to the UI as JSON for the charts, and **openpyxl** builds the Excel file for download.

**Why FastAPI rather than Java Spring Boot?**
It needs far less code, validates data automatically, generates Swagger docs at `/docs`, and is one of the fastest Python frameworks. The 3-tier design would be identical in Spring Boot: controllers = routers, entities = models, DTOs = schemas.

**How would this go to production?**
- Switch to PostgreSQL by changing `DATABASE_URL`.
- Set a strong `JWT_SECRET`.
- Use a real payment gateway (Razorpay or Stripe) with webhook signature verification.
- Run with `ng build` + Nginx and `uvicorn` behind HTTPS.
- Add database migrations with Alembic.

## SDLC phases (for the presentation)
1. **Planning**: problem (stock spread across outlets, manual tracking), scope, two user roles
2. **Requirements**: the feature lists above (functional); security, speed and auditability (non-functional)
3. **Design**: 3-tier architecture, ER diagram, REST API contract, UI screens
4. **Development**: backend first (models → services → routers), then Angular pages
5. **Testing**: pytest API tests + Angular unit tests + manual end-to-end demo
6. **Deployment and maintenance**: production checklist above

Screenshots of every page are in `docs/screenshots/`.
