-- =====================================================================
-- 00_create_user.sql
-- Run ONCE as SYSTEM in SQL Developer (open this file, press F5).
-- Connect SYSTEM using the service name of your PLUGGABLE database:
--   Oracle 26ai Free : FREEPDB1
--   Oracle 21c       : usually ORCLPDB (whatever "Pluggable database name" you chose in the installer)
--   Oracle 21c XE    : XEPDB1
-- Safe to run again. Works on Oracle 19c, 21c, 23ai and 26ai.
-- Creates:
--   INVENTORY       -> owns all project tables (password inventory123)
--   INVENTORY_TEST  -> used only by the automated tests (pytest)
-- =====================================================================
SET SERVEROUTPUT ON

DECLARE
  v_container VARCHAR2(128) := SYS_CONTEXT('USERENV', 'CON_NAME');
  v_pdbs      VARCHAR2(4000);

  PROCEDURE make_user(p_name IN VARCHAR2) IS
    v_count PLS_INTEGER;
  BEGIN
    SELECT COUNT(*) INTO v_count FROM dba_users WHERE username = UPPER(p_name);
    IF v_count = 0 THEN
      EXECUTE IMMEDIATE 'CREATE USER ' || p_name || ' IDENTIFIED BY inventory123'
                     || ' DEFAULT TABLESPACE users QUOTA UNLIMITED ON users';
      DBMS_OUTPUT.PUT_LINE('User ' || UPPER(p_name) || ' created in ' || v_container);
    ELSE
      DBMS_OUTPUT.PUT_LINE('User ' || UPPER(p_name) || ' already exists in ' || v_container);
    END IF;
    EXECUTE IMMEDIATE 'GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW, CREATE SEQUENCE,'
                   || ' CREATE PROCEDURE, CREATE TRIGGER, CREATE TYPE TO ' || p_name;
  END make_user;
BEGIN
  -- Project users must live in a pluggable database, not in the root container.
  IF v_container = 'CDB$ROOT' THEN
    SELECT LISTAGG(name, ', ') WITHIN GROUP (ORDER BY name) INTO v_pdbs
      FROM v$pdbs WHERE name <> 'PDB$SEED';
    RAISE_APPLICATION_ERROR(-20000,
      'You are connected to the root container. Reconnect SYSTEM using the service name of your '
      || 'pluggable database (' || v_pdbs || ') and run this script again.');
  END IF;
  make_user('inventory');
  make_user('inventory_test');
END;
/
