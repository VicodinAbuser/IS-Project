-- =====================================================================
-- 04_demo_queries.sql  -  Queries to run live during the presentation
-- Open in SQL Developer (connected as INVENTORY). Put the cursor on a
-- statement and press Ctrl+Enter to run just that one.
-- =====================================================================

-- 1) What is in the schema?
SELECT object_type, object_name, status
  FROM user_objects
 WHERE object_type IN ('TABLE', 'VIEW', 'PACKAGE', 'PACKAGE BODY', 'TRIGGER')
 ORDER BY object_type, object_name;

-- 2) Stock of every product at every outlet (view)
SELECT * FROM v_inventory_status ORDER BY outlet_name, product_name;

-- 3) Low-stock alerts, the same list the admin dashboard shows
SELECT product_name, outlet_name, quantity, reorder_level
  FROM v_inventory_status WHERE low_stock = 1;

-- 4) Collective stock across all outlets
SELECT * FROM v_product_stock ORDER BY total_stock;

-- 5) Quarterly sales by outlet (what the Reports page charts)
SELECT * FROM v_quarterly_sales ORDER BY sales_year DESC, sales_quarter DESC, revenue DESC;

-- 6) Latest orders with payment and delivery status
SELECT o.order_id, u.full_name, ou.name AS outlet, o.order_status, o.total_amount,
       p.payment_status, d.delivery_status, o.created_at
  FROM orders o
  JOIN app_users u  ON u.user_id   = o.customer_id
  JOIN outlets ou   ON ou.outlet_id = o.outlet_id
  JOIN payments p   ON p.order_id  = o.order_id
  JOIN deliveries d ON d.order_id  = o.order_id
 ORDER BY o.order_id DESC FETCH FIRST 10 ROWS ONLY;

-- ---------------------------------------------------------------------
-- LIVE DEMO: database -> website
-- ---------------------------------------------------------------------
-- 7) Restock from Oracle, then refresh Admin > Inventory in the browser: +50 appears.
EXEC inventory_pkg.restock(p_product_id => 1, p_outlet_id => 1, p_quantity => 50, p_note => 'Restocked from SQL Developer');

-- 8) The trigger logged it automatically:
SELECT movement_type, qty_change, note, created_at
  FROM stock_movements ORDER BY movement_id DESC FETCH FIRST 5 ROWS ONLY;

-- 9) Even a plain UPDATE is logged (as MANUAL) by TRG_INVENTORY_AUDIT. COMMIT so the website sees it.
UPDATE inventory SET quantity = quantity - 1 WHERE product_id = 1 AND outlet_id = 1;
COMMIT;

-- 10) Business rules are enforced in the database: this fails with
--     ORA-20001: Not enough stock ... and nothing is saved.
DECLARE
  v_order_id NUMBER;
BEGIN
  inventory_pkg.place_order(p_customer_id => 2, p_outlet_id => 1, p_shipping_address => '12 Hill Road, Mumbai',
                            p_items_json => '[{"product_id": 2, "quantity": 9999}]', p_order_id => v_order_id);
END;
/

-- 11) Place a real order from Oracle; it then appears in the customer's "My orders" page.
SET SERVEROUTPUT ON
DECLARE
  v_order_id NUMBER;
BEGIN
  inventory_pkg.place_order(p_customer_id => 2, p_outlet_id => 1, p_shipping_address => '12 Hill Road, Mumbai',
                            p_items_json => '[{"product_id": 1, "quantity": 2}, {"product_id": 7, "quantity": 1}]',
                            p_order_id => v_order_id);
  DBMS_OUTPUT.PUT_LINE('Created order #' || v_order_id);
END;
/

-- ---------------------------------------------------------------------
-- LIVE DEMO: website -> database
-- ---------------------------------------------------------------------
-- 12) Buy something in the browser as the customer, then run this: the new order,
--     its items and the SALE stock movements are already in Oracle.
SELECT o.order_id, o.order_status, oi.product_id, oi.quantity, oi.unit_price
  FROM orders o JOIN order_items oi ON oi.order_id = o.order_id
 WHERE o.order_id = (SELECT MAX(order_id) FROM orders);
