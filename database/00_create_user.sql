-- =====================================================================
-- 00_create_user.sql
-- Run ONCE as SYSTEM (or another DBA user) connected to the pluggable
-- database, e.g. in SQL Developer:  SYSTEM @ localhost:1521/FREEPDB1
-- Creates the INVENTORY schema that owns all project tables.
-- =====================================================================
CREATE USER inventory IDENTIFIED BY inventory123
  DEFAULT TABLESPACE users
  QUOTA UNLIMITED ON users;

GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW, CREATE SEQUENCE,
      CREATE PROCEDURE, CREATE TRIGGER, CREATE TYPE TO inventory;

-- Optional: a separate schema used only by the automated tests (pytest),
-- so running tests never wipes your demo data.
CREATE USER inventory_test IDENTIFIED BY inventory123
  DEFAULT TABLESPACE users
  QUOTA UNLIMITED ON users;

GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW, CREATE SEQUENCE,
      CREATE PROCEDURE, CREATE TRIGGER, CREATE TYPE TO inventory_test;
