-- =====================================================================
-- 02_inventory_pkg.sql  -  Stored procedures, triggers and views
--
-- How the work is split between Python and Oracle:
--   * The Python backend (backend/app/services/*.py) holds the BUSINESS LOGIC:
--     who may do what, is there enough stock, may this order still be cancelled,
--     did the payment succeed, which delivery step comes next, ...
--     It runs each action as ONE transaction and commits or rolls back.
--   * This package INVENTORY_PKG is the DATA-OPERATION layer the Python code calls.
--     Each procedure does one well-defined change to the tables (lock a stock row,
--     apply a stock change, create an order, set a payment status, ...). The
--     procedures make no business decisions and never COMMIT: the caller does.
--   * Triggers keep the audit log and the "last updated" times correct automatically,
--     even for changes typed directly in SQL Developer.
--   * Views join the tables into easy-to-read results (customer names, outlet names, ...).
--
-- Run as INVENTORY after 01_schema.sql. Safe to re-run.
-- Try it in SQL Developer, e.g.:
--   EXEC inventory_pkg.apply_stock_change(1, 1, 50, 'RESTOCK', NULL, NULL, 'Demo');
--   COMMIT;
--   SELECT * FROM v_stock_movement_details ORDER BY movement_id DESC FETCH FIRST 5 ROWS ONLY;
-- =====================================================================

CREATE OR REPLACE PACKAGE inventory_pkg AUTHID DEFINER AS
  -- Raised when the row a procedure must change does not exist. The Python API turns it into HTTP 404.
  c_not_found CONSTANT PLS_INTEGER := -20004;

  -- Read by the audit trigger: WHY the stock is changing. They return NULL when someone
  -- ran a plain UPDATE, and the trigger then logs the change as MANUAL.
  FUNCTION ctx_movement_type RETURN VARCHAR2;
  FUNCTION ctx_user_id       RETURN NUMBER;
  FUNCTION ctx_order_id      RETURN NUMBER;
  FUNCTION ctx_note          RETURN VARCHAR2;
  FUNCTION ctx_when          RETURN TIMESTAMP;
  PROCEDURE set_backdate(p_when IN TIMESTAMP);   -- only used by the seed script to back-date history

  -- ----- Stock -----
  -- Locks the stock row (SELECT ... FOR UPDATE) so nobody else can change it until the
  -- caller commits, and returns the units on the shelf. Creates a 0 row the first time.
  PROCEDURE lock_stock(p_product_id IN NUMBER, p_outlet_id IN NUMBER, p_quantity OUT NUMBER);
  -- Adds p_change units (negative = removes). The trigger writes the STOCK_MOVEMENTS row.
  PROCEDURE apply_stock_change(p_product_id IN NUMBER, p_outlet_id IN NUMBER, p_change IN NUMBER,
                               p_movement_type IN VARCHAR2, p_user_id IN NUMBER DEFAULT NULL,
                               p_order_id IN NUMBER DEFAULT NULL, p_note IN VARCHAR2 DEFAULT NULL);
  -- Puts every item of an order back on its outlet's shelf (movement type CANCEL or RETURN).
  PROCEDURE restore_order_stock(p_order_id IN NUMBER, p_movement_type IN VARCHAR2,
                                p_user_id IN NUMBER DEFAULT NULL, p_note IN VARCHAR2 DEFAULT NULL);
  FUNCTION stock_at   (p_product_id IN NUMBER, p_outlet_id IN NUMBER) RETURN NUMBER;
  FUNCTION total_stock(p_product_id IN NUMBER) RETURN NUMBER;

  -- ----- Orders, payments, deliveries -----
  PROCEDURE create_order(p_customer_id IN NUMBER, p_outlet_id IN NUMBER, p_shipping_address IN VARCHAR2,
                         p_order_id OUT NUMBER);
  PROCEDURE add_order_item(p_order_id IN NUMBER, p_product_id IN NUMBER, p_quantity IN NUMBER, p_unit_price IN NUMBER);
  -- Sets the order total and opens its PENDING payment and NOT_SHIPPED delivery.
  PROCEDURE open_payment_and_delivery(p_order_id IN NUMBER, p_total_amount IN NUMBER);
  -- Locks the order (so two requests can't change it at once) and returns its current state.
  PROCEDURE lock_order(p_order_id IN NUMBER, p_customer_id OUT NUMBER, p_outlet_id OUT NUMBER,
                       p_order_status OUT VARCHAR2, p_payment_status OUT VARCHAR2,
                       p_delivery_status OUT VARCHAR2, p_created_at OUT TIMESTAMP);
  PROCEDURE set_order_status(p_order_id IN NUMBER, p_status IN VARCHAR2);
  PROCEDURE set_payment(p_order_id IN NUMBER, p_status IN VARCHAR2, p_method IN VARCHAR2 DEFAULT NULL,
                        p_transaction_ref IN VARCHAR2 DEFAULT NULL);
  PROCEDURE set_delivery(p_order_id IN NUMBER, p_status IN VARCHAR2, p_courier IN VARCHAR2 DEFAULT NULL,
                         p_tracking_number IN VARCHAR2 DEFAULT NULL);

  -- ----- Users and access -----
  PROCEDURE create_user(p_full_name IN VARCHAR2, p_email IN VARCHAR2, p_password_hash IN VARCHAR2,
                        p_user_id OUT NUMBER);
  -- Inserts or updates the customer's personal details (MERGE).
  PROCEDURE save_customer_profile(p_customer_id IN NUMBER, p_phone IN VARCHAR2, p_address_line IN VARCHAR2,
                                  p_city IN VARCHAR2, p_state IN VARCHAR2, p_pincode IN VARCHAR2,
                                  p_preferred_outlet_id IN NUMBER);
  PROCEDURE assign_profile(p_user_id IN NUMBER, p_profile_code IN VARCHAR2, p_assigned_by IN NUMBER DEFAULT NULL);
  PROCEDURE revoke_profile(p_user_id IN NUMBER, p_profile_code IN VARCHAR2);
  PROCEDURE set_account_status(p_user_id IN NUMBER, p_status IN VARCHAR2);
  PROCEDURE update_user_name(p_user_id IN NUMBER, p_full_name IN VARCHAR2);
  -- Marks the user as changed now (e.g. after their profiles changed), for "latest updated" lists.
  PROCEDURE touch_user(p_user_id IN NUMBER);
  PROCEDURE record_login_success(p_user_id IN NUMBER);
  PROCEDURE record_login_failure(p_user_id IN NUMBER, p_locked_until IN TIMESTAMP DEFAULT NULL);
  PROCEDURE unlock_user(p_user_id IN NUMBER);

  -- ----- Catalogue -----
  -- p_product_id NULL = create a new product (its id is returned), otherwise update it.
  PROCEDURE save_product(p_product_id IN OUT NUMBER, p_sku IN VARCHAR2, p_name IN VARCHAR2,
                         p_description IN VARCHAR2, p_price IN NUMBER, p_image_url IN VARCHAR2,
                         p_reorder_level IN NUMBER, p_is_active IN NUMBER, p_category_id IN NUMBER,
                         p_supplier_id IN NUMBER);
  PROCEDURE set_product_active(p_product_id IN NUMBER, p_is_active IN NUMBER);
  PROCEDURE create_outlet(p_name IN VARCHAR2, p_city IN VARCHAR2, p_address IN VARCHAR2, p_outlet_id OUT NUMBER);
END inventory_pkg;
/

CREATE OR REPLACE PACKAGE BODY inventory_pkg AS

  -- Private: only this package can set them; the trigger reads them through the ctx_* functions.
  g_movement_type VARCHAR2(20);
  g_user_id       NUMBER;
  g_order_id      NUMBER;
  g_note          VARCHAR2(255);
  g_when          TIMESTAMP;

  FUNCTION ctx_movement_type RETURN VARCHAR2  IS BEGIN RETURN g_movement_type; END;
  FUNCTION ctx_user_id       RETURN NUMBER    IS BEGIN RETURN g_user_id;       END;
  FUNCTION ctx_order_id      RETURN NUMBER    IS BEGIN RETURN g_order_id;      END;
  FUNCTION ctx_note          RETURN VARCHAR2  IS BEGIN RETURN g_note;          END;
  FUNCTION ctx_when          RETURN TIMESTAMP IS BEGIN RETURN g_when;          END;
  PROCEDURE set_backdate(p_when IN TIMESTAMP) IS BEGIN g_when := p_when;       END;

  PROCEDURE clear_context IS
  BEGIN
    g_movement_type := NULL; g_user_id := NULL; g_order_id := NULL; g_note := NULL;
  END clear_context;

  PROCEDURE not_found_if_none(p_what IN VARCHAR2) IS
  BEGIN
    IF SQL%ROWCOUNT = 0 THEN
      RAISE_APPLICATION_ERROR(c_not_found, p_what || ' not found');
    END IF;
  END not_found_if_none;

  -- ------------------------------------------------------------- stock
  FUNCTION stock_at(p_product_id IN NUMBER, p_outlet_id IN NUMBER) RETURN NUMBER IS
    v_qty NUMBER;
  BEGIN
    SELECT NVL(MAX(quantity), 0) INTO v_qty FROM inventory
     WHERE product_id = p_product_id AND outlet_id = p_outlet_id;
    RETURN v_qty;
  END stock_at;

  FUNCTION total_stock(p_product_id IN NUMBER) RETURN NUMBER IS
    v_qty NUMBER;
  BEGIN
    SELECT NVL(SUM(quantity), 0) INTO v_qty FROM inventory WHERE product_id = p_product_id;
    RETURN v_qty;
  END total_stock;

  PROCEDURE lock_stock(p_product_id IN NUMBER, p_outlet_id IN NUMBER, p_quantity OUT NUMBER) IS
  BEGIN
    SELECT quantity INTO p_quantity FROM inventory
     WHERE product_id = p_product_id AND outlet_id = p_outlet_id
       FOR UPDATE;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN      -- first time this product is stocked at this outlet
      INSERT INTO inventory (product_id, outlet_id, quantity) VALUES (p_product_id, p_outlet_id, 0);
      p_quantity := 0;
  END lock_stock;

  PROCEDURE apply_stock_change(p_product_id IN NUMBER, p_outlet_id IN NUMBER, p_change IN NUMBER,
                               p_movement_type IN VARCHAR2, p_user_id IN NUMBER DEFAULT NULL,
                               p_order_id IN NUMBER DEFAULT NULL, p_note IN VARCHAR2 DEFAULT NULL) IS
    v_qty NUMBER;
  BEGIN
    lock_stock(p_product_id, p_outlet_id, v_qty);
    -- Tell the audit trigger why this change is happening, then update.
    -- (If the result would be below 0, the CHECK constraint on INVENTORY.QUANTITY refuses it.)
    g_movement_type := p_movement_type; g_user_id := p_user_id; g_order_id := p_order_id; g_note := p_note;
    UPDATE inventory
       SET quantity = quantity + p_change, updated_at = NVL(g_when, SYSTIMESTAMP)
     WHERE product_id = p_product_id AND outlet_id = p_outlet_id;
    clear_context;
  EXCEPTION
    WHEN OTHERS THEN clear_context; RAISE;
  END apply_stock_change;

  PROCEDURE restore_order_stock(p_order_id IN NUMBER, p_movement_type IN VARCHAR2,
                                p_user_id IN NUMBER DEFAULT NULL, p_note IN VARCHAR2 DEFAULT NULL) IS
  BEGIN
    -- Sorted by product so two transactions always lock rows in the same order (no deadlocks).
    FOR item IN (SELECT oi.product_id, oi.quantity, o.outlet_id
                   FROM order_items oi JOIN orders o ON o.order_id = oi.order_id
                  WHERE oi.order_id = p_order_id ORDER BY oi.product_id) LOOP
      apply_stock_change(item.product_id, item.outlet_id, item.quantity, p_movement_type, p_user_id, p_order_id, p_note);
    END LOOP;
  END restore_order_stock;

  -- ------------------------------------------------------------- orders
  PROCEDURE create_order(p_customer_id IN NUMBER, p_outlet_id IN NUMBER, p_shipping_address IN VARCHAR2,
                         p_order_id OUT NUMBER) IS
  BEGIN
    INSERT INTO orders (customer_id, outlet_id, shipping_address)
    VALUES (p_customer_id, p_outlet_id, p_shipping_address)
    RETURNING order_id INTO p_order_id;
  END create_order;

  PROCEDURE add_order_item(p_order_id IN NUMBER, p_product_id IN NUMBER, p_quantity IN NUMBER, p_unit_price IN NUMBER) IS
  BEGIN
    INSERT INTO order_items (order_id, product_id, quantity, unit_price)
    VALUES (p_order_id, p_product_id, p_quantity, p_unit_price);
  END add_order_item;

  PROCEDURE open_payment_and_delivery(p_order_id IN NUMBER, p_total_amount IN NUMBER) IS
  BEGIN
    UPDATE orders SET total_amount = p_total_amount WHERE order_id = p_order_id;
    not_found_if_none('Order');
    INSERT INTO payments   (order_id, amount) VALUES (p_order_id, p_total_amount);
    INSERT INTO deliveries (order_id)         VALUES (p_order_id);
  END open_payment_and_delivery;

  PROCEDURE lock_order(p_order_id IN NUMBER, p_customer_id OUT NUMBER, p_outlet_id OUT NUMBER,
                       p_order_status OUT VARCHAR2, p_payment_status OUT VARCHAR2,
                       p_delivery_status OUT VARCHAR2, p_created_at OUT TIMESTAMP) IS
  BEGIN
    SELECT o.customer_id, o.outlet_id, o.order_status, p.payment_status, d.delivery_status, o.created_at
      INTO p_customer_id, p_outlet_id, p_order_status, p_payment_status, p_delivery_status, p_created_at
      FROM orders o
      JOIN payments p   ON p.order_id = o.order_id
      JOIN deliveries d ON d.order_id = o.order_id
     WHERE o.order_id = p_order_id
       FOR UPDATE OF o.order_status;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN RAISE_APPLICATION_ERROR(c_not_found, 'Order not found');
  END lock_order;

  PROCEDURE set_order_status(p_order_id IN NUMBER, p_status IN VARCHAR2) IS
  BEGIN
    UPDATE orders SET order_status = p_status WHERE order_id = p_order_id;
    not_found_if_none('Order');
  END set_order_status;

  PROCEDURE set_payment(p_order_id IN NUMBER, p_status IN VARCHAR2, p_method IN VARCHAR2 DEFAULT NULL,
                        p_transaction_ref IN VARCHAR2 DEFAULT NULL) IS
  BEGIN
    UPDATE payments
       SET payment_status  = p_status,
           payment_method  = NVL(p_method, payment_method),
           transaction_ref = NVL(p_transaction_ref, transaction_ref)
     WHERE order_id = p_order_id;
    not_found_if_none('Payment');
  END set_payment;

  PROCEDURE set_delivery(p_order_id IN NUMBER, p_status IN VARCHAR2, p_courier IN VARCHAR2 DEFAULT NULL,
                         p_tracking_number IN VARCHAR2 DEFAULT NULL) IS
  BEGIN
    UPDATE deliveries
       SET delivery_status = p_status,
           courier         = NVL(p_courier, courier),
           tracking_number = NVL(p_tracking_number, tracking_number)
     WHERE order_id = p_order_id;
    not_found_if_none('Delivery');
  END set_delivery;

  -- ------------------------------------------------------------- users and access
  PROCEDURE create_user(p_full_name IN VARCHAR2, p_email IN VARCHAR2, p_password_hash IN VARCHAR2,
                        p_user_id OUT NUMBER) IS
  BEGIN
    INSERT INTO users (full_name, email, password_hash)
    VALUES (p_full_name, LOWER(p_email), p_password_hash)
    RETURNING user_id INTO p_user_id;
  END create_user;

  PROCEDURE save_customer_profile(p_customer_id IN NUMBER, p_phone IN VARCHAR2, p_address_line IN VARCHAR2,
                                  p_city IN VARCHAR2, p_state IN VARCHAR2, p_pincode IN VARCHAR2,
                                  p_preferred_outlet_id IN NUMBER) IS
  BEGIN
    MERGE INTO customer_profiles c
    USING (SELECT p_customer_id AS customer_id FROM dual) s
       ON (c.customer_id = s.customer_id)
     WHEN MATCHED THEN UPDATE
          SET phone = p_phone, address_line = p_address_line, city = p_city, state = p_state,
              pincode = p_pincode, preferred_outlet_id = p_preferred_outlet_id
     WHEN NOT MATCHED THEN INSERT (customer_id, phone, address_line, city, state, pincode, preferred_outlet_id)
          VALUES (p_customer_id, p_phone, p_address_line, p_city, p_state, p_pincode, p_preferred_outlet_id);
  END save_customer_profile;

  PROCEDURE assign_profile(p_user_id IN NUMBER, p_profile_code IN VARCHAR2, p_assigned_by IN NUMBER DEFAULT NULL) IS
    v_profile_id profiles.profile_id%TYPE;
  BEGIN
    SELECT profile_id INTO v_profile_id FROM profiles WHERE profile_code = p_profile_code;
    INSERT INTO user_profiles (user_id, profile_id, assigned_by)
    SELECT p_user_id, v_profile_id, p_assigned_by FROM dual
     WHERE NOT EXISTS (SELECT 1 FROM user_profiles WHERE user_id = p_user_id AND profile_id = v_profile_id);
  EXCEPTION
    WHEN NO_DATA_FOUND THEN RAISE_APPLICATION_ERROR(c_not_found, 'Profile ' || p_profile_code || ' not found');
  END assign_profile;

  PROCEDURE revoke_profile(p_user_id IN NUMBER, p_profile_code IN VARCHAR2) IS
  BEGIN
    DELETE FROM user_profiles
     WHERE user_id = p_user_id
       AND profile_id = (SELECT profile_id FROM profiles WHERE profile_code = p_profile_code);
  END revoke_profile;

  PROCEDURE set_account_status(p_user_id IN NUMBER, p_status IN VARCHAR2) IS
  BEGIN
    UPDATE users SET account_status = p_status WHERE user_id = p_user_id;
    not_found_if_none('User');
  END set_account_status;

  PROCEDURE update_user_name(p_user_id IN NUMBER, p_full_name IN VARCHAR2) IS
  BEGIN
    UPDATE users SET full_name = p_full_name WHERE user_id = p_user_id;
    not_found_if_none('User');
  END update_user_name;

  PROCEDURE touch_user(p_user_id IN NUMBER) IS
  BEGIN
    UPDATE users SET updated_at = SYSTIMESTAMP WHERE user_id = p_user_id;
  END touch_user;

  PROCEDURE record_login_success(p_user_id IN NUMBER) IS
  BEGIN
    UPDATE users SET failed_login_count = 0, locked_until = NULL, last_login_at = SYSTIMESTAMP
     WHERE user_id = p_user_id;
  END record_login_success;

  PROCEDURE record_login_failure(p_user_id IN NUMBER, p_locked_until IN TIMESTAMP DEFAULT NULL) IS
  BEGIN
    UPDATE users
       SET failed_login_count = CASE WHEN p_locked_until IS NULL THEN failed_login_count + 1 ELSE 0 END,
           locked_until       = p_locked_until
     WHERE user_id = p_user_id;
  END record_login_failure;

  PROCEDURE unlock_user(p_user_id IN NUMBER) IS
  BEGIN
    UPDATE users SET failed_login_count = 0, locked_until = NULL WHERE user_id = p_user_id;
    not_found_if_none('User');
  END unlock_user;

  -- ------------------------------------------------------------- catalogue
  PROCEDURE save_product(p_product_id IN OUT NUMBER, p_sku IN VARCHAR2, p_name IN VARCHAR2,
                         p_description IN VARCHAR2, p_price IN NUMBER, p_image_url IN VARCHAR2,
                         p_reorder_level IN NUMBER, p_is_active IN NUMBER, p_category_id IN NUMBER,
                         p_supplier_id IN NUMBER) IS
  BEGIN
    IF p_product_id IS NULL THEN
      INSERT INTO products (sku, name, description, price, image_url, reorder_level, is_active, category_id, supplier_id)
      VALUES (p_sku, p_name, p_description, p_price, p_image_url, p_reorder_level, p_is_active, p_category_id, p_supplier_id)
      RETURNING product_id INTO p_product_id;
    ELSE
      UPDATE products
         SET sku = p_sku, name = p_name, description = p_description, price = p_price, image_url = p_image_url,
             reorder_level = p_reorder_level, is_active = p_is_active, category_id = p_category_id,
             supplier_id = p_supplier_id
       WHERE product_id = p_product_id;
      not_found_if_none('Product');
    END IF;
  END save_product;

  PROCEDURE set_product_active(p_product_id IN NUMBER, p_is_active IN NUMBER) IS
  BEGIN
    UPDATE products SET is_active = p_is_active WHERE product_id = p_product_id;
    not_found_if_none('Product');
  END set_product_active;

  PROCEDURE create_outlet(p_name IN VARCHAR2, p_city IN VARCHAR2, p_address IN VARCHAR2, p_outlet_id OUT NUMBER) IS
  BEGIN
    INSERT INTO outlets (name, city, address) VALUES (p_name, p_city, p_address)
    RETURNING outlet_id INTO p_outlet_id;
  END create_outlet;

END inventory_pkg;
/

-- =====================================================================
-- Triggers
-- =====================================================================

-- Every change to INVENTORY.QUANTITY is written to STOCK_MOVEMENTS, even a manual
-- UPDATE typed in SQL Developer (logged as MANUAL), so the history can't be skipped.
CREATE OR REPLACE TRIGGER trg_inventory_audit
AFTER INSERT OR UPDATE OF quantity ON inventory
FOR EACH ROW
DECLARE
  v_change NUMBER := :NEW.quantity - NVL(:OLD.quantity, 0);
BEGIN
  IF v_change <> 0 THEN
    INSERT INTO stock_movements (product_id, outlet_id, qty_change, movement_type, note, order_id, user_id, created_at)
    VALUES (:NEW.product_id, :NEW.outlet_id, v_change,
            NVL(inventory_pkg.ctx_movement_type, 'MANUAL'),
            CASE WHEN inventory_pkg.ctx_movement_type IS NULL
                 THEN 'Changed directly in the database by ' || USER
                 ELSE inventory_pkg.ctx_note END,
            inventory_pkg.ctx_order_id, inventory_pkg.ctx_user_id,
            NVL(inventory_pkg.ctx_when, SYSTIMESTAMP));
  END IF;
END;
/

-- "Last updated" times: any UPDATE of these rows stamps UPDATED_AT, unless the statement
-- sets UPDATED_AT itself. The admin and customer screens sort by these columns.
-- For USERS only real account changes count (name, email, password, status), not a login.
CREATE OR REPLACE TRIGGER trg_users_updated
BEFORE UPDATE OF full_name, email, password_hash, account_status ON users FOR EACH ROW
BEGIN
  IF NOT UPDATING('UPDATED_AT') THEN :NEW.updated_at := NVL(inventory_pkg.ctx_when, SYSTIMESTAMP); END IF;
END;
/
CREATE OR REPLACE TRIGGER trg_custprof_updated
BEFORE UPDATE ON customer_profiles FOR EACH ROW
BEGIN
  IF NOT UPDATING('UPDATED_AT') THEN :NEW.updated_at := NVL(inventory_pkg.ctx_when, SYSTIMESTAMP); END IF;
END;
/
CREATE OR REPLACE TRIGGER trg_products_updated
BEFORE UPDATE ON products FOR EACH ROW
BEGIN
  IF NOT UPDATING('UPDATED_AT') THEN :NEW.updated_at := NVL(inventory_pkg.ctx_when, SYSTIMESTAMP); END IF;
END;
/
CREATE OR REPLACE TRIGGER trg_orders_updated
BEFORE UPDATE ON orders FOR EACH ROW
BEGIN
  IF NOT UPDATING('UPDATED_AT') THEN :NEW.updated_at := NVL(inventory_pkg.ctx_when, SYSTIMESTAMP); END IF;
END;
/
-- A change to a payment or delivery also counts as a change to its order,
-- so "latest updated" order lists show it at the top.
CREATE OR REPLACE TRIGGER trg_payments_updated
BEFORE UPDATE ON payments FOR EACH ROW
BEGIN
  IF NOT UPDATING('UPDATED_AT') THEN :NEW.updated_at := NVL(inventory_pkg.ctx_when, SYSTIMESTAMP); END IF;
END;
/
CREATE OR REPLACE TRIGGER trg_payments_touch_order
AFTER UPDATE ON payments FOR EACH ROW
BEGIN
  UPDATE orders SET updated_at = :NEW.updated_at WHERE order_id = :NEW.order_id AND updated_at < :NEW.updated_at;
END;
/
CREATE OR REPLACE TRIGGER trg_deliveries_updated
BEFORE UPDATE ON deliveries FOR EACH ROW
BEGIN
  IF NOT UPDATING('UPDATED_AT') THEN :NEW.updated_at := NVL(inventory_pkg.ctx_when, SYSTIMESTAMP); END IF;
END;
/
CREATE OR REPLACE TRIGGER trg_deliveries_touch_order
AFTER UPDATE ON deliveries FOR EACH ROW
BEGIN
  UPDATE orders SET updated_at = :NEW.updated_at WHERE order_id = :NEW.order_id AND updated_at < :NEW.updated_at;
END;
/

-- =====================================================================
-- Views used by the application
-- =====================================================================
CREATE OR REPLACE VIEW v_inventory_status AS
SELECT i.product_id, p.sku, p.name AS product_name, i.outlet_id, o.name AS outlet_name,
       i.quantity, p.reorder_level,
       CASE WHEN i.quantity <= p.reorder_level THEN 1 ELSE 0 END AS low_stock,
       p.price, i.quantity * p.price AS stock_value, i.updated_at
  FROM inventory i
  JOIN products p ON p.product_id = i.product_id
  JOIN outlets  o ON o.outlet_id  = i.outlet_id
 WHERE p.is_active = 1;

CREATE OR REPLACE VIEW v_product_stock AS
SELECT p.product_id, p.sku, p.name AS product_name, p.price, p.is_active,
       NVL(SUM(i.quantity), 0) AS total_stock,
       NVL(SUM(i.quantity), 0) * p.price AS stock_value
  FROM products p
  LEFT JOIN inventory i ON i.product_id = p.product_id
 GROUP BY p.product_id, p.sku, p.name, p.price, p.is_active;

-- One row per product sold on a PAID order; reports aggregate this.
CREATE OR REPLACE VIEW v_sales_lines AS
SELECT o.order_id, o.created_at,
       EXTRACT(YEAR FROM o.created_at)               AS sales_year,
       TO_NUMBER(TO_CHAR(o.created_at, 'Q'))         AS sales_quarter,
       EXTRACT(MONTH FROM o.created_at)              AS sales_month,
       o.outlet_id, ou.name AS outlet_name,
       oi.product_id, p.sku, p.name AS product_name,
       NVL(c.name, 'Uncategorised')                  AS category_name,
       oi.quantity, oi.unit_price,
       oi.quantity * oi.unit_price                   AS revenue
  FROM orders o
  JOIN order_items oi ON oi.order_id = o.order_id
  JOIN outlets ou     ON ou.outlet_id = o.outlet_id
  JOIN products p     ON p.product_id = oi.product_id
  LEFT JOIN categories c ON c.category_id = p.category_id
 WHERE o.order_status = 'PAID';

CREATE OR REPLACE VIEW v_quarterly_sales AS
SELECT sales_year, sales_quarter, outlet_name,
       COUNT(DISTINCT order_id) AS orders,
       SUM(quantity)            AS units_sold,
       SUM(revenue)             AS revenue
  FROM v_sales_lines
 GROUP BY sales_year, sales_quarter, outlet_name;

-- =====================================================================
-- Readable views for SQL Developer: names instead of ID numbers
-- =====================================================================

-- Every order with the customer's name, the outlet, payment and delivery in one row.
CREATE OR REPLACE VIEW v_order_details AS
SELECT o.order_id, o.created_at AS order_date, o.updated_at AS last_updated, o.order_status,
       o.customer_id, u.full_name AS customer_name, u.email AS customer_email, cp.phone AS customer_phone,
       o.outlet_id, ou.name AS outlet_name, ou.city AS outlet_city,
       (SELECT COUNT(*) FROM order_items oi WHERE oi.order_id = o.order_id)           AS item_lines,
       (SELECT NVL(SUM(oi.quantity), 0) FROM order_items oi WHERE oi.order_id = o.order_id) AS units,
       o.total_amount,
       p.payment_status, p.payment_method, p.transaction_ref, p.updated_at AS payment_updated,
       d.delivery_status, d.courier, d.tracking_number, d.updated_at AS delivery_updated,
       o.shipping_address
  FROM orders o
  JOIN users u        ON u.user_id = o.customer_id
  LEFT JOIN customer_profiles cp ON cp.customer_id = o.customer_id
  JOIN outlets ou     ON ou.outlet_id = o.outlet_id
  LEFT JOIN payments p   ON p.order_id = o.order_id
  LEFT JOIN deliveries d ON d.order_id = o.order_id;

-- Every product line of every order, with names.
CREATE OR REPLACE VIEW v_order_item_details AS
SELECT oi.order_item_id, oi.order_id, o.created_at AS order_date, o.order_status,
       u.full_name AS customer_name, ou.name AS outlet_name,
       p.sku, p.name AS product_name, NVL(c.name, 'Uncategorised') AS category_name,
       oi.quantity, oi.unit_price, oi.quantity * oi.unit_price AS line_total
  FROM order_items oi
  JOIN orders o    ON o.order_id = oi.order_id
  JOIN users u     ON u.user_id = o.customer_id
  JOIN outlets ou  ON ou.outlet_id = o.outlet_id
  JOIN products p  ON p.product_id = oi.product_id
  LEFT JOIN categories c ON c.category_id = p.category_id;

-- The stock audit log with product, outlet and user names.
CREATE OR REPLACE VIEW v_stock_movement_details AS
SELECT m.movement_id, m.created_at, m.movement_type, m.qty_change,
       p.sku, p.name AS product_name, o.name AS outlet_name,
       m.order_id, m.user_id, u.full_name AS changed_by, m.note
  FROM stock_movements m
  JOIN products p ON p.product_id = m.product_id
  JOIN outlets o  ON o.outlet_id  = m.outlet_id
  LEFT JOIN users u ON u.user_id = m.user_id;

-- Who has which access: one row per user x profile x permission.
CREATE OR REPLACE VIEW v_user_access AS
SELECT u.user_id, u.full_name, u.email, u.account_status,
       pr.profile_code, pr.profile_name,
       pe.permission_code, pe.permission_name, pe.module, pe.access_type
  FROM users u
  JOIN user_profiles up  ON up.user_id = u.user_id
  JOIN profiles pr       ON pr.profile_id = up.profile_id
  JOIN authorizations a  ON a.profile_id = pr.profile_id
  JOIN permissions pe    ON pe.permission_id = a.permission_id;

-- The authorization matrix: which profile may do what.
CREATE OR REPLACE VIEW v_profile_permissions AS
SELECT pr.profile_code, pr.profile_name, pr.is_staff,
       pe.module, pe.permission_code, pe.permission_name, pe.access_type, a.granted_at
  FROM profiles pr
  JOIN authorizations a ON a.profile_id = pr.profile_id
  JOIN permissions pe   ON pe.permission_id = a.permission_id;

-- Customers with their details and how much they have bought.
CREATE OR REPLACE VIEW v_customer_details AS
SELECT u.user_id AS customer_id, u.full_name AS customer_name, u.email, cp.phone,
       cp.address_line, cp.city, cp.state, cp.pincode, ou.name AS preferred_outlet,
       u.account_status, u.created_at AS registered_on, u.last_login_at,
       NVL(s.orders, 0) AS orders, NVL(s.paid_orders, 0) AS paid_orders,
       NVL(s.total_spent, 0) AS total_spent, s.last_order_date
  FROM users u
  JOIN user_profiles up ON up.user_id = u.user_id
  JOIN profiles pr      ON pr.profile_id = up.profile_id AND pr.profile_code = 'CUSTOMER'
  LEFT JOIN customer_profiles cp ON cp.customer_id = u.user_id
  LEFT JOIN outlets ou  ON ou.outlet_id = cp.preferred_outlet_id
  LEFT JOIN (SELECT customer_id, COUNT(*) AS orders,
                    SUM(CASE WHEN order_status = 'PAID' THEN 1 ELSE 0 END) AS paid_orders,
                    SUM(CASE WHEN order_status = 'PAID' THEN total_amount ELSE 0 END) AS total_spent,
                    MAX(created_at) AS last_order_date
               FROM orders GROUP BY customer_id) s ON s.customer_id = u.user_id;
