"""Open a connection to Listmanagement_core as dataengine_pipeline.

The password is never in code or config files. It is read from:
  1. Azure Key Vault, if DATAENGINE_KEYVAULT_URL is set
     (secret name: DATAENGINE_KEYVAULT_SECRET, default "dataengine-pipeline-sql"), or
  2. Windows Credential Manager via `keyring`
     (service "dataengine", user "dataengine_pipeline").

Environment:
  DATAENGINE_SQL_SERVER    Managed Instance host name (required)
  DATAENGINE_SQL_DATABASE  target database (default Listmanagement_core)
  DATAENGINE_SQL_DRIVER    ODBC driver (default "ODBC Driver 18 for SQL Server")
"""
from __future__ import annotations

import os

LOGIN = "dataengine_pipeline"
DEFAULT_DATABASE = "Listmanagement_core"
SOURCE_DATABASES = frozenset({"listmanagementdb", "listmanagement_in", "listmanagement_filters"})
KEYRING_SERVICE = "dataengine"


class ConfigError(RuntimeError):
    pass


def target_database() -> str:
    db = os.environ.get("DATAENGINE_SQL_DATABASE", DEFAULT_DATABASE)
    if db.lower() in SOURCE_DATABASES:
        raise ConfigError(f"Refusing to target source database {db!r}; migrations write to the core only.")
    return db


def get_password() -> str:
    vault_url = os.environ.get("DATAENGINE_KEYVAULT_URL")
    if vault_url:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient

        name = os.environ.get("DATAENGINE_KEYVAULT_SECRET", "dataengine-pipeline-sql")
        return SecretClient(vault_url, DefaultAzureCredential()).get_secret(name).value

    import keyring

    password = keyring.get_password(KEYRING_SERVICE, LOGIN)
    if not password:
        raise ConfigError(
            f"No password found in Credential Manager for service {KEYRING_SERVICE!r}, user {LOGIN!r}."
        )
    return password


def connection_string(password: str) -> str:
    server = os.environ.get("DATAENGINE_SQL_SERVER")
    if not server:
        raise ConfigError("Set DATAENGINE_SQL_SERVER to the Managed Instance host name.")
    driver = os.environ.get("DATAENGINE_SQL_DRIVER", "ODBC Driver 18 for SQL Server")
    return (
        f"DRIVER={{{driver}}};SERVER={server};DATABASE={target_database()};"
        f"UID={LOGIN};PWD={{{password}}};Encrypt=yes;TrustServerCertificate=no;"
        "Application Name=dataengine-migrate"
    )


def connect():
    """Return a pyodbc connection with autocommit off."""
    import pyodbc

    return pyodbc.connect(connection_string(get_password()), autocommit=False)
