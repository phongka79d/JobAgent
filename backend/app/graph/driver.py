"""Official Neo4j async driver lifecycle and connectivity check.

Owns open/close and connectivity only. Schema DDL lives in
``app.graph.constraints``. Domain node writes and relationship logic belong
to later plans.
"""

from __future__ import annotations

from neo4j import AsyncDriver, AsyncGraphDatabase

from app.core.settings import Settings


def open_driver(settings: Settings) -> AsyncDriver:
    """Open one official async driver from shared settings.

    Credentials use ``NEO4J_PASSWORD`` as a secret value only for driver auth.
    The password is never written into Cypher, logs, or exception messages here.
    """
    return AsyncGraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(
            settings.NEO4J_USER,
            settings.NEO4J_PASSWORD.get_secret_value(),
        ),
    )


async def close_driver(driver: AsyncDriver) -> None:
    """Close the driver and release its pooled connections."""
    await driver.close()


async def check_connectivity(driver: AsyncDriver) -> bool:
    """Return True when the driver can reach Neo4j; False on connectivity failure.

    Does not mutate schema or write domain data. Failures are reported as
    ``False`` without embedding secrets into the return value.
    """
    try:
        await driver.verify_connectivity()
    except Exception:
        return False
    return True
