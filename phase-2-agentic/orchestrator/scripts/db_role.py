"""One-time: the orchestrator's own Postgres role and schema (run as the admin via make)."""

import os
import sys

import psycopg
from psycopg import sql

EXPECTED_SYSTEM_ID = 7701263628382191654
ROLE, SCHEMA, DATABASE = "platform_v2_orchestrator", "orchestrator", "platform_v2"


def main() -> None:
    """Create or update the orchestrator's database role."""
    with psycopg.connect(
        host="127.0.0.1",
        port=15432,
        dbname=DATABASE,
        user="platform_v2_admin",
        password=os.environ["PG_ADMIN_PASSWORD"],
        autocommit=True,
    ) as conn:
        found = conn.execute("SELECT system_identifier FROM pg_control_system()").fetchone()
        if found is None or found[0] != EXPECTED_SYSTEM_ID:
            sys.exit("not the expected database: nothing changed")
        password = sql.Literal(os.environ["PG_ORCHESTRATOR_PASSWORD"])
        exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (ROLE,)).fetchone()
        verb = "ALTER" if exists else "CREATE"
        conn.execute(
            sql.SQL(verb + " ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE").format(
                sql.Identifier(ROLE), password
            )
        )
        for statement in (
            "GRANT CONNECT ON DATABASE {db} TO {role}",
            "CREATE SCHEMA IF NOT EXISTS {schema} AUTHORIZATION {role}",
            "ALTER ROLE {role} IN DATABASE {db} SET search_path = {schema}",
        ):
            conn.execute(
                sql.SQL(statement).format(
                    db=sql.Identifier(DATABASE),
                    role=sql.Identifier(ROLE),
                    schema=sql.Identifier(SCHEMA),
                )
            )
        print(f"{verb.lower()}d role {ROLE}; schema {SCHEMA} ready")


if __name__ == "__main__":
    main()
