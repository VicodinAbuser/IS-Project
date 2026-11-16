-- =====================================================================
-- 04_demo_queries.sql  -  Live demo script for SQL Developer
-- Connect as INVENTORY. Run each statement with Ctrl+Enter (one at a time),
-- or the whole file with F5. Keep the website open next to it.
-- =====================================================================

-- 1. Everything the project created in Oracle (all should be VALID)
SELECT object_type, object_name, status FROM user_objects
 WHERE object_type IN ('TABLE', 'VIEW', 'PACKAGE', 'PACKAGE BODY', 'TRIGGER')
 ORDER BY object_type, object_name;

-- 2. What each table and column means (descriptions stored with COMMENT ON)
SELECT table_name, comments FROM user_tab_comments WHERE comments IS NOT NULL ORDER BY table_name;
SELECT column_name, comments FROM user_col_comments WHERE table_name = 'ORDERS' ORDER BY column_name;

-- 3. Users, profiles and access rights
--    The authorization matrix: which profile has which permission
SELECT profile_name, module, permission_code, access_type
  FROM v_profile_permissions ORDER BY profile_name, module, permission_code;
--    How many users have each profile
SELECT p.profile_name, COUNT(up.user_id) AS users
  FROM profiles p LEFT JOIN user_profiles up ON up.profile_id = p.profile_id
 GROUP BY p.profile_name ORDER BY users DESC;
--    What one user may do
SELECT full_name, profile_code, permission_code, access_type
  FROM v_user_access WHERE email = 'manager@inventory.com' ORDER BY permission_code;

-- 4. Customers with their details and spending (no ID numbers to look up)
SELECT customer_name, email, phone, city, pincode, preferred_outlet, orders, total_spent, last_order_date
  FROM v_customer_details ORDER BY total_spent DESC FETCH FIRST 10 ROWS ONLY;

-- 5. Orders with customer name, outlet, payment and delivery in one row - latest updated first
SELECT order_id, order_date, last_updated, customer_name, outlet_name, units, total_amount,
       order_status, payment_status, delivery_status
  FROM v_order_details ORDER BY last_updated DESC FETCH FIRST 15 ROWS ONLY;

-- 6. Stock per outlet and low-stock alerts
SELECT outlet_name, product_name, quantity, reorder_level, updated_at
  FROM v_inventory_status WHERE low_stock = 1 ORDER BY quantity;
SELECT product_name, total_stock, stock_value FROM v_product_stock WHERE is_active = 1 ORDER BY total_stock DESC;

-- 7. Quarterly sales (the same view the Reports page uses)
SELECT sales_year, sales_quarter, outlet_name, orders, units_sold, revenue
  FROM v_quarterly_sales ORDER BY sales_year, sales_quarter, revenue DESC;

-- 8. DATABASE -> WEBSITE: change stock with a stored procedure, then refresh the website's Inventory page.
--    (The website does the same: Python checks the rules, then calls these procedures.)
DECLARE
  v_qty NUMBER;
BEGIN
  inventory_pkg.lock_stock(1, 1, v_qty);                                    -- product 1 at outlet 1, row locked
  inventory_pkg.apply_stock_change(1, 1, 50, 'RESTOCK', 1, NULL, 'Demo from SQL Developer');
  COMMIT;                                                                   -- the procedures never commit by themselves
END;
/
SELECT * FROM v_inventory_status WHERE product_id = 1 AND outlet_id = 1;

-- 9. The trigger wrote the audit log automatically (with who made the change)
SELECT * FROM v_stock_movement_details ORDER BY movement_id DESC FETCH FIRST 5 ROWS ONLY;

-- 10. Even a plain UPDATE is logged, as MANUAL
UPDATE inventory SET quantity = quantity - 1 WHERE product_id = 1 AND outlet_id = 1;
COMMIT;
SELECT movement_type, qty_change, note FROM stock_movements ORDER BY movement_id DESC FETCH FIRST 1 ROWS ONLY;

-- 11. Oracle's own safety net: stock can never go below 0 (CHECK constraint)
--     This fails with ORA-02290: check constraint (CK_INVENTORY_QTY) violated, and nothing changes.
UPDATE inventory SET quantity = quantity - 999999 WHERE product_id = 1 AND outlet_id = 1;
ROLLBACK;

-- 12. "Last updated" is maintained by triggers: change a delivery, and its order moves to the top
UPDATE deliveries SET courier = courier
 WHERE order_id = (SELECT MIN(order_id) FROM orders WHERE order_status = 'PAID');
COMMIT;
SELECT order_id, order_date, last_updated, customer_name, delivery_status
  FROM v_order_details ORDER BY last_updated DESC FETCH FIRST 3 ROWS ONLY;

-- 13. WEBSITE -> DATABASE: place an order in the browser, then run this - it's the first row
SELECT order_id, last_updated, customer_name, total_amount, payment_status, delivery_status
  FROM v_order_details ORDER BY order_id DESC FETCH FIRST 5 ROWS ONLY;
