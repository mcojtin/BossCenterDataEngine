-- Bootstrap for the migration runner: records which migration scripts ran.
-- Created by sql/runner/migrate.py before any migration. Re-runnable.
IF OBJECT_ID(N'dbo.SchemaVersion', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.SchemaVersion (
        ScriptName varchar(200) NOT NULL,
        Checksum   char(64)     NOT NULL,
        AppliedAt  datetime2(3) NOT NULL CONSTRAINT DF_SchemaVersion_AppliedAt DEFAULT SYSUTCDATETIME(),
        AppliedBy  sysname      NOT NULL CONSTRAINT DF_SchemaVersion_AppliedBy DEFAULT SUSER_SNAME(),
        DurationMs int          NOT NULL,
        CONSTRAINT PK_SchemaVersion PRIMARY KEY (ScriptName)
    );
END;
