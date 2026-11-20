-- V001__core_schema.sql
-- Core schema for Listmanagement_core: every table the pipeline writes to.
--
-- Run against Listmanagement_core only (sql/runner/migrate.py does this).
-- Re-runnable: every object is created only if it does not already exist.
-- Additive only: nothing in this script removes, empties or rewrites data.
-- Source databases are never referenced here.

-- ---------------------------------------------------------------------------
-- PipelineRun: one row per step run. Every other table records the RunID
-- that wrote it, so a step can skip work it already did.
-- ---------------------------------------------------------------------------
IF OBJECT_ID(N'dbo.PipelineRun', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.PipelineRun (
        RunID       bigint IDENTITY(1,1) NOT NULL,
        StepName    varchar(50)   NOT NULL,
        StartedAt   datetime2(3)  NOT NULL CONSTRAINT DF_PipelineRun_StartedAt DEFAULT SYSUTCDATETIME(),
        FinishedAt  datetime2(3)  NULL,
        Status      varchar(20)   NOT NULL CONSTRAINT DF_PipelineRun_Status DEFAULT 'running',
        RowsIn      int           NULL,
        RowsOut     int           NULL,
        Message     varchar(2000) NULL,
        CONSTRAINT PK_PipelineRun PRIMARY KEY (RunID),
        CONSTRAINT CK_PipelineRun_Status CHECK (Status IN ('running', 'succeeded', 'failed'))
    );
END;
GO

-- ---------------------------------------------------------------------------
-- Person: one row per real person, keyed by standardized phone + last name.
-- ---------------------------------------------------------------------------
IF OBJECT_ID(N'dbo.Person', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Person (
        PersonID     bigint IDENTITY(1,1) NOT NULL,
        PhoneStd     varchar(15)  NOT NULL,
        LastNameStd  varchar(50)  NOT NULL,
        FirstSeenAt  datetime2(3) NOT NULL,
        CreatedRunID bigint       NOT NULL,
        CONSTRAINT PK_Person PRIMARY KEY (PersonID),
        CONSTRAINT UQ_Person_PhoneStd_LastNameStd UNIQUE (PhoneStd, LastNameStd),
        CONSTRAINT FK_Person_PipelineRun FOREIGN KEY (CreatedRunID) REFERENCES dbo.PipelineRun (RunID)
    );
END;
GO

-- ---------------------------------------------------------------------------
-- LeadEvent: one row per opt-in (one source In row).
-- SourceInID is the In table's ID; with VerticalID it names the source row,
-- so the same In row can never be loaded twice.
-- OfferID and VerticalID refer to ListmanagementDB (no cross-database FK).
-- ---------------------------------------------------------------------------
IF OBJECT_ID(N'dbo.LeadEvent', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.LeadEvent (
        LeadEventID        bigint IDENTITY(1,1) NOT NULL,
        PersonID           bigint       NULL,
        VerticalID         int          NOT NULL,
        OfferID            int          NULL,
        SourceInID         int          NOT NULL,
        LeadID             varchar(50)  NULL,
        TrustedToken       varchar(250) NULL,
        OptInTimeStamp     datetime2(3) NULL,
        DuplicateOfEventID bigint       NULL,
        RunID              bigint       NOT NULL,
        LoadedAt           datetime2(3) NOT NULL CONSTRAINT DF_LeadEvent_LoadedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_LeadEvent PRIMARY KEY (LeadEventID),
        CONSTRAINT UQ_LeadEvent_Vertical_SourceIn UNIQUE (VerticalID, SourceInID),
        CONSTRAINT FK_LeadEvent_Person FOREIGN KEY (PersonID) REFERENCES dbo.Person (PersonID),
        CONSTRAINT FK_LeadEvent_DuplicateOf FOREIGN KEY (DuplicateOfEventID) REFERENCES dbo.LeadEvent (LeadEventID),
        CONSTRAINT FK_LeadEvent_PipelineRun FOREIGN KEY (RunID) REFERENCES dbo.PipelineRun (RunID),
        CONSTRAINT CK_LeadEvent_NotSelfDuplicate CHECK (DuplicateOfEventID IS NULL OR DuplicateOfEventID <> LeadEventID)
    );
END;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_LeadEvent_PersonID' AND object_id = OBJECT_ID(N'dbo.LeadEvent'))
    CREATE INDEX IX_LeadEvent_PersonID ON dbo.LeadEvent (PersonID);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_LeadEvent_OfferID' AND object_id = OBJECT_ID(N'dbo.LeadEvent'))
    CREATE INDEX IX_LeadEvent_OfferID ON dbo.LeadEvent (OfferID);
GO

-- ---------------------------------------------------------------------------
-- Contact: name, phone and email per event. Raw value kept next to the
-- standardized one; Std columns are filled by the standardize step.
-- ---------------------------------------------------------------------------
IF OBJECT_ID(N'dbo.Contact', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Contact (
        LeadEventID   bigint       NOT NULL,
        FirstNameRaw  varchar(50)  NULL,
        FirstNameStd  varchar(50)  NULL,
        LastNameRaw   varchar(50)  NULL,
        LastNameStd   varchar(50)  NULL,
        HomePhoneRaw  varchar(20)  NULL,
        HomePhoneStd  varchar(15)  NULL,
        CellPhoneRaw  varchar(20)  NULL,
        CellPhoneStd  varchar(15)  NULL,
        EmailRaw      varchar(100) NULL,
        EmailStd      varchar(100) NULL,
        RunID         bigint       NOT NULL,
        CONSTRAINT PK_Contact PRIMARY KEY (LeadEventID),
        CONSTRAINT FK_Contact_LeadEvent FOREIGN KEY (LeadEventID) REFERENCES dbo.LeadEvent (LeadEventID),
        CONSTRAINT FK_Contact_PipelineRun FOREIGN KEY (RunID) REFERENCES dbo.PipelineRun (RunID)
    );
END;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_Contact_HomePhoneStd' AND object_id = OBJECT_ID(N'dbo.Contact'))
    CREATE INDEX IX_Contact_HomePhoneStd ON dbo.Contact (HomePhoneStd);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_Contact_EmailStd' AND object_id = OBJECT_ID(N'dbo.Contact'))
    CREATE INDEX IX_Contact_EmailStd ON dbo.Contact (EmailStd);
GO

-- ---------------------------------------------------------------------------
-- Address: postal address per event, raw next to standardized.
-- ---------------------------------------------------------------------------
IF OBJECT_ID(N'dbo.Address', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Address (
        LeadEventID  bigint       NOT NULL,
        AddressRaw   varchar(100) NULL,
        AddressStd   varchar(150) NULL,
        CityRaw      varchar(50)  NULL,
        CityStd      varchar(50)  NULL,
        StateRaw     varchar(25)  NULL,
        StateStd     char(2)      NULL,
        ZipRaw       varchar(25)  NULL,
        ZipStd       varchar(10)  NULL,
        CountyRaw    varchar(150) NULL,
        CountyStd    varchar(150) NULL,
        RunID        bigint       NOT NULL,
        CONSTRAINT PK_Address PRIMARY KEY (LeadEventID),
        CONSTRAINT FK_Address_LeadEvent FOREIGN KEY (LeadEventID) REFERENCES dbo.LeadEvent (LeadEventID),
        CONSTRAINT FK_Address_PipelineRun FOREIGN KEY (RunID) REFERENCES dbo.PipelineRun (RunID)
    );
END;
GO

-- ---------------------------------------------------------------------------
-- QualityFlag: one row per problem found on an event. FieldName is '' for
-- flags that apply to the whole record.
-- ---------------------------------------------------------------------------
IF OBJECT_ID(N'dbo.QualityFlag', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.QualityFlag (
        QualityFlagID bigint IDENTITY(1,1) NOT NULL,
        LeadEventID   bigint       NOT NULL,
        FlagCode      varchar(50)  NOT NULL,
        FieldName     varchar(128) NOT NULL CONSTRAINT DF_QualityFlag_FieldName DEFAULT '',
        Detail        varchar(500) NULL,
        RunID         bigint       NOT NULL,
        CreatedAt     datetime2(3) NOT NULL CONSTRAINT DF_QualityFlag_CreatedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_QualityFlag PRIMARY KEY (QualityFlagID),
        CONSTRAINT UQ_QualityFlag_Event_Code_Field UNIQUE (LeadEventID, FlagCode, FieldName),
        CONSTRAINT FK_QualityFlag_LeadEvent FOREIGN KEY (LeadEventID) REFERENCES dbo.LeadEvent (LeadEventID),
        CONSTRAINT FK_QualityFlag_PipelineRun FOREIGN KEY (RunID) REFERENCES dbo.PipelineRun (RunID)
    );
END;
GO

-- ---------------------------------------------------------------------------
-- DNC: do-not-contact list. Value is the standardized phone, email or
-- address string.
-- ---------------------------------------------------------------------------
IF OBJECT_ID(N'dbo.DNC', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.DNC (
        DNCID      bigint IDENTITY(1,1) NOT NULL,
        DNCType    varchar(10)  NOT NULL,
        Value      varchar(400) NOT NULL,
        Reason     varchar(200) NOT NULL,
        DateAdded  datetime2(3) NOT NULL CONSTRAINT DF_DNC_DateAdded DEFAULT SYSUTCDATETIME(),
        Source     varchar(100) NULL,
        CONSTRAINT PK_DNC PRIMARY KEY (DNCID),
        CONSTRAINT UQ_DNC_Type_Value UNIQUE (DNCType, Value),
        CONSTRAINT CK_DNC_Type CHECK (DNCType IN ('phone', 'email', 'address'))
    );
END;
GO

-- ---------------------------------------------------------------------------
-- RecordStatus: current status of each event. Records are never deleted;
-- duplicates and blocked records are flagged here with a reason.
-- ---------------------------------------------------------------------------
IF OBJECT_ID(N'dbo.RecordStatus', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.RecordStatus (
        LeadEventID bigint       NOT NULL,
        Status      varchar(20)  NOT NULL,
        Reason      varchar(200) NULL,
        RunID       bigint       NOT NULL,
        UpdatedAt   datetime2(3) NOT NULL CONSTRAINT DF_RecordStatus_UpdatedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_RecordStatus PRIMARY KEY (LeadEventID),
        CONSTRAINT CK_RecordStatus_Status CHECK (Status IN ('active', 'duplicate', 'blocked')),
        CONSTRAINT CK_RecordStatus_ReasonRequired CHECK (Status = 'active' OR Reason IS NOT NULL),
        CONSTRAINT FK_RecordStatus_LeadEvent FOREIGN KEY (LeadEventID) REFERENCES dbo.LeadEvent (LeadEventID),
        CONSTRAINT FK_RecordStatus_PipelineRun FOREIGN KEY (RunID) REFERENCES dbo.PipelineRun (RunID)
    );
END;
GO

-- ---------------------------------------------------------------------------
-- DuplicateReport: each duplicate found by a dedupe run, with the rule that
-- matched it.
-- ---------------------------------------------------------------------------
IF OBJECT_ID(N'dbo.DuplicateReport', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.DuplicateReport (
        DuplicateReportID  bigint IDENTITY(1,1) NOT NULL,
        RunID              bigint       NOT NULL,
        LeadEventID        bigint       NOT NULL,
        DuplicateOfEventID bigint       NOT NULL,
        MatchRule          varchar(100) NOT NULL,
        CreatedAt          datetime2(3) NOT NULL CONSTRAINT DF_DuplicateReport_CreatedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_DuplicateReport PRIMARY KEY (DuplicateReportID),
        CONSTRAINT UQ_DuplicateReport_Run_Event UNIQUE (RunID, LeadEventID),
        CONSTRAINT FK_DuplicateReport_PipelineRun FOREIGN KEY (RunID) REFERENCES dbo.PipelineRun (RunID),
        CONSTRAINT FK_DuplicateReport_LeadEvent FOREIGN KEY (LeadEventID) REFERENCES dbo.LeadEvent (LeadEventID),
        CONSTRAINT FK_DuplicateReport_DuplicateOf FOREIGN KEY (DuplicateOfEventID) REFERENCES dbo.LeadEvent (LeadEventID)
    );
END;
GO

-- ---------------------------------------------------------------------------
-- FieldMap: which source column goes to which core column. Included = 0 rows
-- document fields deliberately kept out (for example Insurance health fields).
-- ---------------------------------------------------------------------------
IF OBJECT_ID(N'dbo.FieldMap', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.FieldMap (
        FieldMapID    int IDENTITY(1,1) NOT NULL,
        VerticalID    int          NOT NULL,
        SourceTable   varchar(256) NOT NULL,
        SourceColumn  varchar(128) NOT NULL,
        CoreTable     varchar(128) NULL,
        CoreColumn    varchar(128) NULL,
        Included      bit          NOT NULL,
        ExcludeReason varchar(200) NULL,
        UpdatedAt     datetime2(3) NOT NULL CONSTRAINT DF_FieldMap_UpdatedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_FieldMap PRIMARY KEY (FieldMapID),
        CONSTRAINT UQ_FieldMap_Source UNIQUE (VerticalID, SourceTable, SourceColumn),
        CONSTRAINT CK_FieldMap_Target CHECK (
            (Included = 1 AND CoreTable IS NOT NULL AND CoreColumn IS NOT NULL)
            OR (Included = 0 AND ExcludeReason IS NOT NULL))
    );
END;
GO

-- ---------------------------------------------------------------------------
-- Watermark: how far each step has read in each source table.
-- ---------------------------------------------------------------------------
IF OBJECT_ID(N'dbo.Watermark', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Watermark (
        SourceTable  varchar(256) NOT NULL,
        StepName     varchar(50)  NOT NULL,
        LastSourceID bigint       NOT NULL,
        LastRunID    bigint       NOT NULL,
        UpdatedAt    datetime2(3) NOT NULL CONSTRAINT DF_Watermark_UpdatedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_Watermark PRIMARY KEY (SourceTable, StepName),
        CONSTRAINT FK_Watermark_PipelineRun FOREIGN KEY (LastRunID) REFERENCES dbo.PipelineRun (RunID)
    );
END;
GO

-- ---------------------------------------------------------------------------
-- OfferType: core side table that adds a type (for example 'co-reg') to each
-- Offer. The source Offer table is never altered. OfferID is a logical link
-- only (no cross-database FK).
-- ---------------------------------------------------------------------------
IF OBJECT_ID(N'dbo.OfferType', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.OfferType (
        OfferID   int          NOT NULL,
        OfferType varchar(50)  NOT NULL,
        UpdatedAt datetime2(3) NOT NULL CONSTRAINT DF_OfferType_UpdatedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_OfferType PRIMARY KEY (OfferID)
    );
END;
GO

-- ---------------------------------------------------------------------------
-- Per-vertical typed attribute tables. One row per (event, value source):
-- 'lead' = the value as received; 'enriched' = a value added later (1B).
-- Generated from VerticalField; do not edit by hand.
-- ---------------------------------------------------------------------------
-- BEGIN GENERATED ATTR TABLES (tools/gen_attr_ddl.py)
-- Mortgage (VerticalID 1)
IF OBJECT_ID(N'dbo.MortgageAttr', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.MortgageAttr (
        LeadEventID   bigint       NOT NULL,
        ValueSource   varchar(10)  NOT NULL,
        RunID         bigint       NOT NULL,
        LoadedAt      datetime2(3) NOT NULL CONSTRAINT DF_MortgageAttr_LoadedAt DEFAULT SYSUTCDATETIME(),
        [DateOfBirth] varchar(25) NULL,
        [VAStatus] varchar(25) NULL,
        [CreditGrade] varchar(25) NULL,
        [EstimatedHomeValue] decimal(14,3) NULL,
        [PropertyType] varchar(50) NULL,
        [LoanType] varchar(50) NULL,
        [InterestRate] decimal(14,3) NULL,
        [MortgageBalance] decimal(14,3) NULL,
        [CashOut] decimal(14,3) NULL,
        [FHALoan] varchar(50) NULL,
        [LoanTerm] varchar(25) NULL,
        [LoanAmount] decimal(14,3) NULL,
        [VALoan] varchar(50) NULL,
        [ShorterTerm] varchar(50) NULL,
        [NewRateInterested] varchar(50) NULL,
        [ARMInterested] varchar(50) NULL,
        [DateReceived] varchar(50) NULL,
        [Comments] varchar(100) NULL,
        [IPAddress] varchar(50) NULL,
        [LTV] decimal(14,3) NULL,
        [RateType] varchar(50) NULL,
        [Lender] varchar(100) NULL,
        [Product] varchar(150) NULL,
        [Age] varchar(50) NULL,
        [AgentFound] varchar(50) NULL,
        [MovingDate] varchar(100) NULL,
        [TrustedURL] varchar(250) NULL,
        [EstimatedDownPayment] decimal(14,3) NULL,
        [EstimatedDownPaymentPercent] decimal(14,3) NULL,
        [LandingPage] varchar(500) NULL,
        [AppointmentMonth] varchar(25) NULL,
        [AppointmentDay] varchar(25) NULL,
        [AppointmentYear] varchar(25) NULL,
        [UTM_Source] varchar(250) NULL,
        [SUB_ID] varchar(250) NULL,
        [SUB_ID_2] varchar(250) NULL,
        [Publisher] varchar(250) NULL,
        [DebtAmt] varchar(250) NULL,
        [MortgagePayment] varchar(250) NULL,
        CONSTRAINT PK_MortgageAttr PRIMARY KEY (LeadEventID, ValueSource),
        CONSTRAINT CK_MortgageAttr_ValueSource CHECK (ValueSource IN ('lead', 'enriched')),
        CONSTRAINT FK_MortgageAttr_LeadEvent FOREIGN KEY (LeadEventID) REFERENCES dbo.LeadEvent (LeadEventID),
        CONSTRAINT FK_MortgageAttr_PipelineRun FOREIGN KEY (RunID) REFERENCES dbo.PipelineRun (RunID)
    );
END;
GO
-- Insurance (VerticalID 4)
IF OBJECT_ID(N'dbo.InsuranceAttr', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.InsuranceAttr (
        LeadEventID   bigint       NOT NULL,
        ValueSource   varchar(10)  NOT NULL,
        RunID         bigint       NOT NULL,
        LoadedAt      datetime2(3) NOT NULL CONSTRAINT DF_InsuranceAttr_LoadedAt DEFAULT SYSUTCDATETIME(),
        [DateOfBirth] varchar(25) NULL,
        [Publisher] varchar(200) NULL,
        [Product] varchar(150) NULL,
        [IPAddress] varchar(50) NULL,
        [HouseholdSize] varchar(50) NULL,
        [Gender] varchar(50) NULL,
        [Uninsurable] varchar(50) NULL,
        [HeightFeet] varchar(50) NULL,
        [HeightInches] varchar(50) NULL,
        [Weight] decimal(14,3) NULL,
        [Smoker] varchar(50) NULL,
        [CurrentlyInsured] varchar(50) NULL,
        [HealthConditions] varchar(50) NULL,
        [NumberOfChildren] decimal(14,3) NULL,
        [Education] varchar(100) NULL,
        [Student] varchar(50) NULL,
        [ResidenceType] varchar(50) NULL,
        [Occupation] varchar(100) NULL,
        [Comments] varchar(100) NULL,
        [DateReceived] varchar(50) NULL,
        [HouseholdIncome] varchar(50) NULL,
        [MaritalStatus] varchar(100) NULL,
        [LandingPage] varchar(500) NULL,
        [CarYear] varchar(50) NULL,
        [CarMake] varchar(100) NULL,
        [CarModel] varchar(100) NULL,
        [CarTrim] varchar(250) NULL,
        [TCPAText] varchar(500) NULL,
        [UserAgent] varchar(500) NULL,
        [CreditGrade] varchar(25) NULL,
        [RecentConcern] varchar(25) NULL,
        [CoverageType] varchar(100) NULL,
        [CoverageAmount] varchar(25) NULL,
        [PropertyAge] varchar(50) NULL,
        [Construction] varchar(50) NULL,
        [Foundation] varchar(50) NULL,
        [RoofType] varchar(50) NULL,
        [ElectricalSystem] varchar(50) NULL,
        [SecuritySystem] varchar(50) NULL,
        [GarageType] varchar(50) NULL,
        [SquareFeet] varchar(50) NULL,
        [Stories] varchar(50) NULL,
        [Bedrooms] varchar(50) NULL,
        [Bathrooms] varchar(50) NULL,
        [OccupancyType] varchar(50) NULL,
        [ValueofHome] varchar(50) NULL,
        [CoverageAmountSeeking] varchar(50) NULL,
        [Deductible] varchar(50) NULL,
        [Liability] varchar(50) NULL,
        [PropertyType] varchar(50) NULL,
        [ElectricProvider] varchar(100) NULL,
        [ElectricBillMonthlyAmount] varchar(100) NULL,
        [RoofShade] varchar(100) NULL,
        [HomeOwner] varchar(100) NULL,
        [InsuredSince] varchar(25) NULL,
        [TrustedURL] varchar(250) NULL,
        [SUB_ID] varchar(250) NULL,
        [SUB_ID_2] varchar(250) NULL,
        CONSTRAINT PK_InsuranceAttr PRIMARY KEY (LeadEventID, ValueSource),
        CONSTRAINT CK_InsuranceAttr_ValueSource CHECK (ValueSource IN ('lead', 'enriched')),
        CONSTRAINT FK_InsuranceAttr_LeadEvent FOREIGN KEY (LeadEventID) REFERENCES dbo.LeadEvent (LeadEventID),
        CONSTRAINT FK_InsuranceAttr_PipelineRun FOREIGN KEY (RunID) REFERENCES dbo.PipelineRun (RunID)
    );
END;
GO
-- Solar (VerticalID 5)
IF OBJECT_ID(N'dbo.SolarAttr', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.SolarAttr (
        LeadEventID   bigint       NOT NULL,
        ValueSource   varchar(10)  NOT NULL,
        RunID         bigint       NOT NULL,
        LoadedAt      datetime2(3) NOT NULL CONSTRAINT DF_SolarAttr_LoadedAt DEFAULT SYSUTCDATETIME(),
        [DateOfBirth] varchar(25) NULL,
        [Product] varchar(150) NULL,
        [IPAddress] varchar(50) NULL,
        [Comments] varchar(100) NULL,
        [DateReceived] varchar(50) NULL,
        [ElectricUtility] varchar(150) NULL,
        [CreditGrade] varchar(25) NULL,
        [ElectricBill] varchar(100) NULL,
        [RoofShade] varchar(100) NULL,
        [OwnOrRent] varchar(50) NULL,
        [AuthorizedForPropertyChanges] varchar(50) NULL,
        [PropertyStories] varchar(50) NULL,
        [RoofType] varchar(100) NULL,
        [TrustedURL] varchar(250) NULL,
        [Disposition] varchar(150) NULL,
        [LandingPage] varchar(500) NULL,
        [TCPAText] varchar(500) NULL,
        [UserAgent] varchar(500) NULL,
        [OverlayID] varchar(200) NULL,
        [SUB_ID] varchar(250) NULL,
        [SUB_ID_2] varchar(250) NULL,
        [Publisher] varchar(250) NULL,
        CONSTRAINT PK_SolarAttr PRIMARY KEY (LeadEventID, ValueSource),
        CONSTRAINT CK_SolarAttr_ValueSource CHECK (ValueSource IN ('lead', 'enriched')),
        CONSTRAINT FK_SolarAttr_LeadEvent FOREIGN KEY (LeadEventID) REFERENCES dbo.LeadEvent (LeadEventID),
        CONSTRAINT FK_SolarAttr_PipelineRun FOREIGN KEY (RunID) REFERENCES dbo.PipelineRun (RunID)
    );
END;
GO
-- Student (VerticalID 7)
IF OBJECT_ID(N'dbo.StudentAttr', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.StudentAttr (
        LeadEventID   bigint       NOT NULL,
        ValueSource   varchar(10)  NOT NULL,
        RunID         bigint       NOT NULL,
        LoadedAt      datetime2(3) NOT NULL CONSTRAINT DF_StudentAttr_LoadedAt DEFAULT SYSUTCDATETIME(),
        [DateOfBirth] varchar(25) NULL,
        [Publisher] varchar(200) NULL,
        [Product] varchar(150) NULL,
        [IPAddress] varchar(50) NULL,
        [Comments] varchar(250) NULL,
        [DateReceived] varchar(50) NULL,
        [LoanType] varchar(50) NULL,
        [DebtAmount] decimal(14,3) NULL,
        [TrustedURL] varchar(250) NULL,
        [CreditGrade] varchar(25) NULL,
        [OverlayID] varchar(200) NULL,
        [ValidationFlag] varchar(25) NULL,
        [SUB_ID_2] varchar(250) NULL,
        [SUB_ID] varchar(250) NULL,
        [Source_ID] varchar(250) NULL,
        [LandingPage] varchar(500) NULL,
        CONSTRAINT PK_StudentAttr PRIMARY KEY (LeadEventID, ValueSource),
        CONSTRAINT CK_StudentAttr_ValueSource CHECK (ValueSource IN ('lead', 'enriched')),
        CONSTRAINT FK_StudentAttr_LeadEvent FOREIGN KEY (LeadEventID) REFERENCES dbo.LeadEvent (LeadEventID),
        CONSTRAINT FK_StudentAttr_PipelineRun FOREIGN KEY (RunID) REFERENCES dbo.PipelineRun (RunID)
    );
END;
GO
-- HomeOwner (VerticalID 12)
IF OBJECT_ID(N'dbo.HomeOwnerAttr', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.HomeOwnerAttr (
        LeadEventID   bigint       NOT NULL,
        ValueSource   varchar(10)  NOT NULL,
        RunID         bigint       NOT NULL,
        LoadedAt      datetime2(3) NOT NULL CONSTRAINT DF_HomeOwnerAttr_LoadedAt DEFAULT SYSUTCDATETIME(),
        [DateOfBirth] varchar(25) NULL,
        [Gender] varchar(25) NULL,
        [Publisher] varchar(200) NULL,
        [Product] varchar(150) NULL,
        [IPAddress] varchar(50) NULL,
        [Comments] varchar(250) NULL,
        [DateReceived] varchar(50) NULL,
        [TrustedURL] varchar(250) NULL,
        [CreditGrade] varchar(25) NULL,
        [ElectricBill] varchar(100) NULL,
        [ElectricUtility] varchar(150) NULL,
        [OwnOrRent] varchar(50) NULL,
        [OptIn] varchar(500) NULL,
        [RoofShade] varchar(100) NULL,
        [PrimaryLanguage] varchar(100) NULL,
        [TCPA_Language] varchar(500) NULL,
        [LandingPage] varchar(250) NULL,
        [NumWindows] varchar(100) NULL,
        [RoofingProject] varchar(250) NULL,
        [Country] varchar(100) NULL,
        [ProjectType] varchar(250) NULL,
        [Age] varchar(50) NULL,
        [Kids] varchar(50) NULL,
        [MaritalStatus] varchar(100) NULL,
        [HouseHoldIncome] varchar(50) NULL,
        [NetWorth] varchar(50) NULL,
        CONSTRAINT PK_HomeOwnerAttr PRIMARY KEY (LeadEventID, ValueSource),
        CONSTRAINT CK_HomeOwnerAttr_ValueSource CHECK (ValueSource IN ('lead', 'enriched')),
        CONSTRAINT FK_HomeOwnerAttr_LeadEvent FOREIGN KEY (LeadEventID) REFERENCES dbo.LeadEvent (LeadEventID),
        CONSTRAINT FK_HomeOwnerAttr_PipelineRun FOREIGN KEY (RunID) REFERENCES dbo.PipelineRun (RunID)
    );
END;
GO
-- END GENERATED ATTR TABLES
