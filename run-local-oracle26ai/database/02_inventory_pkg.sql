-- =====================================================================
-- 02_inventory_pkg.sql  -  Business logic inside Oracle (PL/SQL)
--   * Package INVENTORY_PKG : stored procedures used by the Python API
--   * Trigger TRG_INVENTORY_AUDIT : logs EVERY stock change automatically
--   * Views : used by the dashboard and quarterly reports
-- Run as INVENTORY after 01_schema.sql. Safe to re-run.
--
-- Try it in SQL Developer, e.g.:
--   EXEC inventory_pkg.restock(p_product_id => 1, p_outlet_id => 1, p_quantity => 50, p_note => 'Demo');
--   SELECT * FROM v_inventory_status WHERE product_id = 1;
--   SELECT * FROM stock_movements ORDER BY movement_id DESC FETCH FIRST 5 ROWS ONLY;
-- =====================================================================

CREATE OR REPLACE PACKAGE inventory_pkg AUTHID DEFINER AS
  -- Error codes raised to the caller. The Python API turns them into HTTP errors.
  c_not_enough_stock CONSTANT PLS_INTEGER := -20001;   -- -> HTTP 409
  c_not_found        CONSTANT PLS_INTEGER := -20004;   -- -> HTTP 404
  c_invalid_state    CONSTANT PLS_INTEGER := -20009;   -- -> HTTP 409
  c_bad_input        CONSTANT PLS_INTEGER := -20022;   -- -> HTTP 422

  -- Unpaid orders older than this are cancelled automatically and their stock released.
  c_payment_timeout_minutes CONSTANT PLS_INTEGER := 30;

  -- Read by the audit trigger: WHY the stock is changing. They return NULL when someone
  -- ran a plain UPDATE, and the trigger then logs the change as MANUAL.
  FUNCTION ctx_movement_type RETURN VARCHAR2;
  FUNCTION ctx_user_id       RETURN NUMBER;
  FUNCTION ctx_order_id      RETURN NUMBER;
  FUNCTION ctx_note          RETURN VARCHAR2;
  FUNCTION ctx_when          RETURN TIMESTAMP;
  PROCEDURE set_backdate(p_when IN TIMESTAMP);   -- only used by the seed script to back-date history

  -- ----- Stock management (admin) -----
  PROCEDURE restock       (p_product_id IN NUMBER, p_outlet_id IN NUMBER, p_quantity IN NUMBER,
                           p_note IN VARCHAR2 DEFAULT NULL, p_user_id IN NUMBER DEFAULT NULL);
  PROCEDURE adjust_stock  (p_product_id IN NUMBER, p_outlet_id IN NUMBER, p_change IN NUMBER,
                           p_note IN VARCHAR2, p_user_id IN NUMBER DEFAULT NULL);
  PROCEDURE transfer_stock(p_product_id IN NUMBER, p_from_outlet_id IN NUMBER, p_to_outlet_id IN NUMBER,
                           p_quantity IN NUMBER, p_note IN VARCHAR2 DEFAULT NULL, p_user_id IN NUMBER DEFAULT NULL);

  -- ----- Orders, payment, delivery -----
  -- p_items_json example: '[{"product_id":1,"quantity":2},{"product_id":5,"quantity":1}]'
  PROCEDURE place_order    (p_customer_id IN NUMBER, p_outlet_id IN NUMBER, p_shipping_address IN VARCHAR2,
                            p_items_json IN CLOB, p_order_id OUT NUMBER);
  PROCEDURE record_payment (p_order_id IN NUMBER, p_method IN VARCHAR2, p_success IN NUMBER,
                            p_transaction_ref IN VARCHAR2 DEFAULT NULL);
  PROCEDURE cancel_order   (p_order_id IN NUMBER, p_user_id IN NUMBER DEFAULT NULL);
  PROCEDURE update_delivery(p_order_id IN NUMBER, p_status IN VARCHAR2,
                            p_courier IN VARCHAR2 DEFAULT NULL, p_tracking_number IN VARCHAR2 DEFAULT NULL);
  -- Cancels PENDING_PAYMENT orders older than p_older_than_minutes and returns their stock.
  -- Called automatically at the start of every PLACE_ORDER. p_expired = how many were cancelled.
  PROCEDURE expire_unpaid_orders(p_older_than_minutes IN NUMBER DEFAULT c_payment_timeout_minutes,
                                 p_expired OUT NUMBER);

  -- ----- Helpers -----
  FUNCTION stock_at   (p_product_id IN NUMBER, p_outlet_id IN NUMBER) RETURN NUMBER;
  FUNCTION total_stock(p_product_id IN NUMBER) RETURN NUMBER;

  -- Core rule used by all procedures above (does not commit).
  PROCEDURE change_stock(p_product_id IN NUMBER, p_outlet_id IN NUMBER, p_change IN NUMBER,
                         p_movement_type IN VARCHAR2, p_user_id IN NUMBER DEFAULT NULL,
                         p_order_id IN NUMBER DEFAULT NULL, p_note IN VARCHAR2 DEFAULT NULL);
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

  PROCEDURE assert_exists(p_table IN VARCHAR2, p_id IN NUMBER) IS
    v_count PLS_INTEGER;
  BEGIN
    IF p_table = 'PRODUCT' THEN
      SELECT COUNT(*) INTO v_count FROM products WHERE product_id = p_id;
    ELSIF p_table = 'OUTLET' THEN
      SELECT COUNT(*) INTO v_count FROM outlets WHERE outlet_id = p_id;
    END IF;
    IF v_count = 0 THEN
      RAISE_APPLICATION_ERROR(c_not_found, INITCAP(p_table) || ' ' || p_id || ' not found');
    END IF;
  END assert_exists;

  FUNCTION stock_at(p_product_id IN NUMBER, p_outlet_id IN NUMBER) RETURN NUMBER IS
    v_qty NUMBER;
  BEGIN
    SELECT NVL(MAX(quantity), 0) INTO v_qty
      FROM inventory WHERE product_id = p_product_id AND outlet_id = p_outlet_id;
    RETURN v_qty;
  END stock_at;

  FUNCTION total_stock(p_product_id IN NUMBER) RETURN NUMBER IS
    v_qty NUMBER;
  BEGIN
    SELECT NVL(SUM(quantity), 0) INTO v_qty FROM inventory WHERE product_id = p_product_id;
    RETURN v_qty;
  END total_stock;

  PROCEDURE change_stock(p_product_id IN NUMBER, p_outlet_id IN NUMBER, p_change IN NUMBER,
                         p_movement_type IN VARCHAR2, p_user_id IN NUMBER DEFAULT NULL,
                         p_order_id IN NUMBER DEFAULT NULL, p_note IN VARCHAR2 DEFAULT NULL) IS
    v_qty  inventory.quantity%TYPE;
    v_name products.name%TYPE;
  BEGIN
    assert_exists('PRODUCT', p_product_id);
    assert_exists('OUTLET', p_outlet_id);

    -- Lock this stock row so two buyers can't take the last unit at the same time.
    BEGIN
      SELECT quantity INTO v_qty FROM inventory
       WHERE product_id = p_product_id AND outlet_id = p_outlet_id
         FOR UPDATE;
    EXCEPTION
      WHEN NO_DATA_FOUND THEN      -- first time this product is stocked at this outlet
        INSERT INTO inventory (product_id, outlet_id, quantity) VALUES (p_product_id, p_outlet_id, 0);
        v_qty := 0;
    END;

    IF v_qty + p_change < 0 THEN
      SELECT name INTO v_name FROM products WHERE product_id = p_product_id;
      RAISE_APPLICATION_ERROR(c_not_enough_stock,
        'Not enough stock for ''' || v_name || ''' at this outlet (available: ' || v_qty || ')');
    END IF;

    -- Tell the audit trigger why this change is happening, then update.
    g_movement_type := p_movement_type; g_user_id := p_user_id; g_order_id := p_order_id; g_note := p_note;
    UPDATE inventory
       SET quantity = quantity + p_change, updated_at = SYSTIMESTAMP
     WHERE product_id = p_product_id AND outlet_id = p_outlet_id;
    clear_context;
  EXCEPTION
    WHEN OTHERS THEN clear_context; RAISE;
  END change_stock;

  -- Put every item of an order back on its outlet's shelf (no commit).
  PROCEDURE return_items_to_stock(p_order_id IN NUMBER, p_outlet_id IN NUMBER, p_movement_type IN VARCHAR2,
                                  p_user_id IN NUMBER, p_note IN VARCHAR2) IS
  BEGIN
    FOR item IN (SELECT product_id, quantity FROM order_items WHERE order_id = p_order_id ORDER BY product_id) LOOP
      change_stock(item.product_id, p_outlet_id, item.quantity, p_movement_type, p_user_id, p_order_id, p_note);
    END LOOP;
  END return_items_to_stock;

  -- Cancel one order that hasn't shipped (no commit). Used by cancel_order and expire_unpaid_orders.
  PROCEDURE do_cancel(p_order_id IN NUMBER, p_outlet_id IN NUMBER, p_user_id IN NUMBER, p_note IN VARCHAR2) IS
  BEGIN
    return_items_to_stock(p_order_id, p_outlet_id, 'CANCEL', p_user_id, p_note);
    -- Paid -> the money goes back (REFUNDED); never paid -> the open payment is closed (CANCELLED).
    UPDATE payments
       SET payment_status = CASE payment_status WHEN 'SUCCESS' THEN 'REFUNDED' ELSE 'CANCELLED' END,
           updated_at = SYSTIMESTAMP
     WHERE order_id = p_order_id AND payment_status IN ('SUCCESS', 'PENDING', 'FAILED');
    UPDATE orders SET order_status = 'CANCELLED' WHERE order_id = p_order_id;
  END do_cancel;

  PROCEDURE restock(p_product_id IN NUMBER, p_outlet_id IN NUMBER, p_quantity IN NUMBER,
                    p_note IN VARCHAR2 DEFAULT NULL, p_user_id IN NUMBER DEFAULT NULL) IS
  BEGIN
    IF p_quantity IS NULL OR p_quantity <= 0 THEN
      RAISE_APPLICATION_ERROR(c_bad_input, 'Quantity must be greater than 0');
    END IF;
    change_stock(p_product_id, p_outlet_id, p_quantity, 'RESTOCK', p_user_id, NULL,
                 NVL(p_note, 'New stock received'));
    COMMIT;
  EXCEPTION
    WHEN OTHERS THEN ROLLBACK; RAISE;
  END restock;

  PROCEDURE adjust_stock(p_product_id IN NUMBER, p_outlet_id IN NUMBER, p_change IN NUMBER,
                         p_note IN VARCHAR2, p_user_id IN NUMBER DEFAULT NULL) IS
  BEGIN
    IF NVL(p_change, 0) = 0 THEN
      RAISE_APPLICATION_ERROR(c_bad_input, 'Change cannot be 0');
    END IF;
    IF LENGTH(TRIM(p_note)) IS NULL OR LENGTH(TRIM(p_note)) < 3 THEN
      RAISE_APPLICATION_ERROR(c_bad_input, 'A reason (note) is required for adjustments');
    END IF;
    change_stock(p_product_id, p_outlet_id, p_change, 'ADJUSTMENT', p_user_id, NULL, p_note);
    COMMIT;
  EXCEPTION
    WHEN OTHERS THEN ROLLBACK; RAISE;
  END adjust_stock;

  PROCEDURE transfer_stock(p_product_id IN NUMBER, p_from_outlet_id IN NUMBER, p_to_outlet_id IN NUMBER,
                           p_quantity IN NUMBER, p_note IN VARCHAR2 DEFAULT NULL, p_user_id IN NUMBER DEFAULT NULL) IS
  BEGIN
    IF p_from_outlet_id = p_to_outlet_id THEN
      RAISE_APPLICATION_ERROR(c_bad_input, 'Choose two different outlets');
    END IF;
    IF p_quantity IS NULL OR p_quantity <= 0 THEN
      RAISE_APPLICATION_ERROR(c_bad_input, 'Quantity must be greater than 0');
    END IF;
    -- Both steps are in ONE transaction: either both happen or neither does.
    change_stock(p_product_id, p_from_outlet_id, -p_quantity, 'TRANSFER_OUT', p_user_id, NULL, p_note);
    change_stock(p_product_id, p_to_outlet_id,    p_quantity, 'TRANSFER_IN',  p_user_id, NULL, p_note);
    COMMIT;
  EXCEPTION
    WHEN OTHERS THEN ROLLBACK; RAISE;
  END transfer_stock;

  PROCEDURE place_order(p_customer_id IN NUMBER, p_outlet_id IN NUMBER, p_shipping_address IN VARCHAR2,
                        p_items_json IN CLOB, p_order_id OUT NUMBER) IS
    v_price  products.price%TYPE;
    v_active products.is_active%TYPE;
    v_total   NUMBER := 0;
    v_lines   PLS_INTEGER := 0;
    v_expired NUMBER;
  BEGIN
    assert_exists('OUTLET', p_outlet_id);
    -- First release stock held by abandoned checkouts, then check availability.
    expire_unpaid_orders(c_payment_timeout_minutes, v_expired);
    IF LENGTH(TRIM(p_shipping_address)) IS NULL OR LENGTH(TRIM(p_shipping_address)) < 5 THEN
      RAISE_APPLICATION_ERROR(c_bad_input, 'Shipping address is too short');
    END IF;

    INSERT INTO orders (customer_id, outlet_id, shipping_address)
    VALUES (p_customer_id, p_outlet_id, p_shipping_address)
    RETURNING order_id INTO p_order_id;

    -- Read the cart from JSON; duplicates are merged. Sorted by product to avoid deadlocks.
    FOR item IN (
      SELECT product_id, SUM(quantity) AS quantity
        FROM JSON_TABLE(p_items_json, '$[*]'
               COLUMNS (product_id NUMBER PATH '$.product_id',
                        quantity   NUMBER PATH '$.quantity'))
       GROUP BY product_id
       ORDER BY product_id
    ) LOOP
      IF item.product_id IS NULL OR NVL(item.quantity, 0) <= 0 THEN
        RAISE_APPLICATION_ERROR(c_bad_input, 'Each item needs a product_id and a quantity above 0');
      END IF;
      BEGIN
        SELECT price, is_active INTO v_price, v_active FROM products WHERE product_id = item.product_id;
      EXCEPTION
        WHEN NO_DATA_FOUND THEN v_active := 0;
      END;
      IF v_active = 0 THEN
        RAISE_APPLICATION_ERROR(c_not_found, 'Product ' || item.product_id || ' not available');
      END IF;

      change_stock(item.product_id, p_outlet_id, -item.quantity, 'SALE', p_customer_id, p_order_id,
                   'Order #' || p_order_id);
      INSERT INTO order_items (order_id, product_id, quantity, unit_price)
      VALUES (p_order_id, item.product_id, item.quantity, v_price);
      v_total := v_total + v_price * item.quantity;
      v_lines := v_lines + 1;
    END LOOP;

    IF v_lines = 0 THEN
      RAISE_APPLICATION_ERROR(c_bad_input, 'Order has no items');
    END IF;

    UPDATE orders SET total_amount = v_total WHERE order_id = p_order_id;
    INSERT INTO payments   (order_id, amount) VALUES (p_order_id, v_total);
    INSERT INTO deliveries (order_id)         VALUES (p_order_id);
    COMMIT;
  EXCEPTION
    WHEN OTHERS THEN
      ROLLBACK;            -- all or nothing: no half-placed orders, no lost stock
      p_order_id := NULL;
      RAISE;
  END place_order;

  PROCEDURE record_payment(p_order_id IN NUMBER, p_method IN VARCHAR2, p_success IN NUMBER,
                           p_transaction_ref IN VARCHAR2 DEFAULT NULL) IS
    v_status orders.order_status%TYPE;
  BEGIN
    BEGIN
      SELECT order_status INTO v_status FROM orders WHERE order_id = p_order_id FOR UPDATE;
    EXCEPTION
      WHEN NO_DATA_FOUND THEN RAISE_APPLICATION_ERROR(c_not_found, 'Order not found');
    END;
    IF v_status <> 'PENDING_PAYMENT' THEN
      RAISE_APPLICATION_ERROR(c_invalid_state, 'Order is ' || v_status || ', cannot pay');
    END IF;

    IF p_success = 1 THEN
      UPDATE payments
         SET payment_status = 'SUCCESS', payment_method = p_method, updated_at = SYSTIMESTAMP,
             transaction_ref = NVL(p_transaction_ref, 'TXN-' || SUBSTR(RAWTOHEX(SYS_GUID()), 1, 12))
       WHERE order_id = p_order_id;
      UPDATE orders     SET order_status = 'PAID' WHERE order_id = p_order_id;
      UPDATE deliveries SET delivery_status = 'PACKED', updated_at = SYSTIMESTAMP WHERE order_id = p_order_id;
    ELSE
      -- Declined: order stays PENDING_PAYMENT so the customer can try again.
      UPDATE payments SET payment_status = 'FAILED', payment_method = p_method, updated_at = SYSTIMESTAMP
       WHERE order_id = p_order_id;
    END IF;
    COMMIT;
  EXCEPTION
    WHEN OTHERS THEN ROLLBACK; RAISE;
  END record_payment;

  PROCEDURE cancel_order(p_order_id IN NUMBER, p_user_id IN NUMBER DEFAULT NULL) IS
    v_status   orders.order_status%TYPE;
    v_outlet   orders.outlet_id%TYPE;
    v_delivery deliveries.delivery_status%TYPE;
  BEGIN
    BEGIN
      SELECT o.order_status, o.outlet_id, d.delivery_status INTO v_status, v_outlet, v_delivery
        FROM orders o JOIN deliveries d ON d.order_id = o.order_id
       WHERE o.order_id = p_order_id
         FOR UPDATE OF o.order_status;
    EXCEPTION
      WHEN NO_DATA_FOUND THEN RAISE_APPLICATION_ERROR(c_not_found, 'Order not found');
    END;
    IF v_status = 'CANCELLED' THEN
      RAISE_APPLICATION_ERROR(c_invalid_state, 'Order already cancelled');
    END IF;
    IF v_delivery NOT IN ('NOT_SHIPPED', 'PACKED') THEN
      RAISE_APPLICATION_ERROR(c_invalid_state, 'Order already shipped, cannot cancel');
    END IF;

    do_cancel(p_order_id, v_outlet, p_user_id, 'Order #' || p_order_id || ' cancelled');
    COMMIT;
  EXCEPTION
    WHEN OTHERS THEN ROLLBACK; RAISE;
  END cancel_order;

  PROCEDURE update_delivery(p_order_id IN NUMBER, p_status IN VARCHAR2,
                            p_courier IN VARCHAR2 DEFAULT NULL, p_tracking_number IN VARCHAR2 DEFAULT NULL) IS
    v_status  orders.order_status%TYPE;
    v_outlet  orders.outlet_id%TYPE;
    v_current deliveries.delivery_status%TYPE;

    -- Position in the delivery journey; a delivery may only move forward.
    FUNCTION step(p IN VARCHAR2) RETURN PLS_INTEGER IS
    BEGIN
      RETURN CASE p WHEN 'NOT_SHIPPED' THEN 0 WHEN 'PACKED' THEN 1 WHEN 'SHIPPED' THEN 2
                    WHEN 'OUT_FOR_DELIVERY' THEN 3 WHEN 'DELIVERED' THEN 4 WHEN 'RETURNED' THEN 5 END;
    END step;
  BEGIN
    BEGIN
      SELECT o.order_status, o.outlet_id, d.delivery_status INTO v_status, v_outlet, v_current
        FROM orders o JOIN deliveries d ON d.order_id = o.order_id
       WHERE o.order_id = p_order_id
         FOR UPDATE OF o.order_status;
    EXCEPTION
      WHEN NO_DATA_FOUND THEN RAISE_APPLICATION_ERROR(c_not_found, 'Order not found');
    END;
    IF v_status <> 'PAID' THEN
      RAISE_APPLICATION_ERROR(c_invalid_state, 'Only paid orders can be shipped (this order is ' || v_status || ')');
    END IF;
    IF step(p_status) IS NULL THEN
      RAISE_APPLICATION_ERROR(c_bad_input, 'Unknown delivery status ' || p_status);
    END IF;
    IF step(p_status) < step(v_current) THEN
      RAISE_APPLICATION_ERROR(c_invalid_state, 'Delivery cannot go back from ' || v_current || ' to ' || p_status);
    END IF;
    IF p_status = 'RETURNED' AND v_current NOT IN ('SHIPPED', 'OUT_FOR_DELIVERY', 'DELIVERED') THEN
      RAISE_APPLICATION_ERROR(c_invalid_state, 'Only shipped orders can be returned; cancel it instead');
    END IF;

    UPDATE deliveries
       SET delivery_status = p_status,
           courier         = NVL(p_courier, courier),
           tracking_number = NVL(p_tracking_number, tracking_number),
           updated_at      = SYSTIMESTAMP
     WHERE order_id = p_order_id;

    IF p_status = 'RETURNED' THEN
      -- Goods came back: restock them at the outlet and refund the customer.
      return_items_to_stock(p_order_id, v_outlet, 'RETURN', NULL, 'Order #' || p_order_id || ' returned');
      UPDATE payments SET payment_status = 'REFUNDED', updated_at = SYSTIMESTAMP
       WHERE order_id = p_order_id AND payment_status = 'SUCCESS';
      UPDATE orders SET order_status = 'RETURNED' WHERE order_id = p_order_id;
    END IF;
    COMMIT;
  EXCEPTION
    WHEN OTHERS THEN ROLLBACK; RAISE;
  END update_delivery;

  PROCEDURE expire_unpaid_orders(p_older_than_minutes IN NUMBER DEFAULT c_payment_timeout_minutes,
                                 p_expired OUT NUMBER) IS
  BEGIN
    p_expired := 0;
    FOR o IN (SELECT order_id, outlet_id FROM orders
               WHERE order_status = 'PENDING_PAYMENT'
                 AND created_at < CAST(SYSTIMESTAMP AS TIMESTAMP)   -- same type as the column, so the index is usable
                                  - NUMTODSINTERVAL(p_older_than_minutes, 'MINUTE')
               ORDER BY order_id
                 FOR UPDATE SKIP LOCKED) LOOP     -- skip an order someone is paying for right now
      do_cancel(o.order_id, o.outlet_id, NULL,
                'Order #' || o.order_id || ' not paid within ' || p_older_than_minutes || ' minutes');
      p_expired := p_expired + 1;
    END LOOP;
    -- No COMMIT here: the caller (e.g. PLACE_ORDER) commits it with its own work.
  END expire_unpaid_orders;

END inventory_pkg;
/

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

-- ---------- Views ----------
CREATE OR REPLACE VIEW v_inventory_status AS
SELECT i.product_id, p.sku, p.name AS product_name, i.outlet_id, o.name AS outlet_name,
       i.quantity, p.reorder_level,
       CASE WHEN i.quantity <= p.reorder_level THEN 1 ELSE 0 END AS low_stock,
       p.price, i.quantity * p.price AS stock_value
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
