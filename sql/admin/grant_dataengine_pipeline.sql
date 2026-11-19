-- grant_dataengine_pipeline.sql
-- One-time permissions for the core-schema migration (item 2).
--
-- Run by a DBA with an admin login, in SSMS or sqlcmd, once per instance
-- (dev Managed Instance first, then prod). Pipeline code never runs this file
-- and never uses an admin login.
--
-- Assumes the dataengine_pipeline LOGIN already exists and already has its
-- read-only users in ListmanagementDB, Listmanagement_in and
-- Listmanagement_filters. Nothing here grants any write on those databases.
-- Safe to re-run.

-- ---------------------------------------------------------------------------
-- 1. Server level: read the instance storage stats (master.sys.server_resource_stats)
--    and DMVs used by the storage check. Read-only permission.
-- ---------------------------------------------------------------------------
USE master;
GO
GRANT VIEW SERVER STATE TO [dataengine_pipeline];
GO

-- ---------------------------------------------------------------------------
-- 2. Listmanagement_core: create the database if it is missing, then give
--    dataengine_pipeline DDL + read/write there, plus ALTER DATABASE so the
--    preflight can set compatibility_level = 160.
-- ---------------------------------------------------------------------------
IF DB_ID(N'Listmanagement_core') IS NULL
    CREATE DATABASE [Listmanagement_core];
GO
USE [Listmanagement_core];
GO
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'dataengine_pipeline')
    CREATE USER [dataengine_pipeline] FOR LOGIN [dataengine_pipeline];
GO
ALTER ROLE db_ddladmin   ADD MEMBER [dataengine_pipeline];
ALTER ROLE db_datareader ADD MEMBER [dataengine_pipeline];
ALTER ROLE db_datawriter ADD MEMBER [dataengine_pipeline];
GRANT ALTER ON DATABASE::[Listmanagement_core] TO [dataengine_pipeline];
GO

-- ---------------------------------------------------------------------------
-- 3. DEV ONLY: an empty test database for tests/sql/test_migration_integration.py.
--    Run this section on the dev Managed Instance only.
-- ---------------------------------------------------------------------------
IF DB_ID(N'Listmanagement_core_test') IS NULL
    CREATE DATABASE [Listmanagement_core_test];
GO
USE [Listmanagement_core_test];
GO
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'dataengine_pipeline')
    CREATE USER [dataengine_pipeline] FOR LOGIN [dataengine_pipeline];
GO
ALTER ROLE db_ddladmin   ADD MEMBER [dataengine_pipeline];
ALTER ROLE db_datareader ADD MEMBER [dataengine_pipeline];
ALTER ROLE db_datawriter ADD MEMBER [dataengine_pipeline];
GRANT ALTER ON DATABASE::[Listmanagement_core_test] TO [dataengine_pipeline];
GO

-- ---------------------------------------------------------------------------
-- 4. Check (read-only): what dataengine_pipeline can do in each database.
-- ---------------------------------------------------------------------------
USE [Listmanagement_core];
GO
SELECT DB_NAME() AS db, r.name AS role_name
FROM sys.database_role_members m
JOIN sys.database_principals r ON r.principal_id = m.role_principal_id
JOIN sys.database_principals u ON u.principal_id = m.member_principal_id
WHERE u.name = N'dataengine_pipeline';
GO
