-- =====================================================================
-- 00_create_user.sql
-- Run ONCE as SYSTEM in SQL Developer (open this file, press F5).
-- Works whether your SYSTEM connection uses service name FREE or FREEPDB1,
-- and is safe to run again.
-- Creates:
--   INVENTORY       -> owns all project tables (password inventory123)
--   INVENTORY_TEST  -> used only by the automated tests (pytest)
-- =====================================================================

-- Project data must live in the pluggable database FREEPDB1, not the root container.
ALTER SESSION SET CONTAINER = FREEPDB1;

CREATE USER IF NOT EXISTS inventory IDENTIFIED BY inventory123
  DEFAULT TABLESPACE users
  QUOTA UNLIMITED ON users;

GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW, CREATE SEQUENCE,
      CREATE PROCEDURE, CREATE TRIGGER, CREATE TYPE TO inventory;

CREATE USER IF NOT EXISTS inventory_test IDENTIFIED BY inventory123
  DEFAULT TABLESPACE users
  QUOTA UNLIMITED ON users;

GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW, CREATE SEQUENCE,
      CREATE PROCEDURE, CREATE TRIGGER, CREATE TYPE TO inventory_test;
