# Copyright (c) 2024 Microsoft Corporation.
# Licensed under the MIT License

"""Neo4j-first data loader for query operations."""

import asyncio
import logging
import os
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# Try to import Neo4j load functions
try:
    from graphrag.graphrag.graph.neo4j_client import (
        load_communities_from_neo4j,
        load_community_reports_from_neo4j,
        load_documents_from_neo4j,
        load_entities_from_neo4j,
        load_relationships_from_neo4j,
        load_text_units_from_neo4j,
    )
    NEO4J_AVAILABLE = True
    NEO4J_LOADERS = {
        "entities": load_entities_from_neo4j,
        "communities": load_communities_from_neo4j,
        "community_reports": load_community_reports_from_neo4j,
        "relationships": load_relationships_from_neo4j,
        "text_units": load_text_units_from_neo4j,
        "documents": load_documents_from_neo4j,
    }
except ImportError:
    NEO4J_AVAILABLE = False
    NEO4J_LOADERS = {}


def _is_neo4j_enabled() -> bool:
    """Check if Neo4j is enabled via environment variable."""
    return os.getenv("GRAPHRAG_USE_NEO4J", "false").lower() == "true"


def _try_neo4j_load(name: str) -> pd.DataFrame | None:
    """Try loading from Neo4j, return None if unavailable or empty."""
    if not (_is_neo4j_enabled() and NEO4J_AVAILABLE and name in NEO4J_LOADERS):
        return None
    try:
        df = NEO4J_LOADERS[name]()
        return df if not df.empty else None
    except Exception as e:
        logger.warning(f"Failed to load {name} from Neo4j: {e}")
        return None


def load_from_neo4j_or_storage(
    name: str, storage_loader: Any, *args: Any, **kwargs: Any
) -> pd.DataFrame:
    """Load data from Neo4j first, fallback to storage."""
    if df := _try_neo4j_load(name):
        logger.debug(f"Loaded {name} from Neo4j ({len(df)} rows)")
        return df
    logger.debug(f"Loading {name} from storage")
    return storage_loader(*args, **kwargs) if callable(storage_loader) else storage_loader


async def load_async_from_neo4j_or_storage(
    name: str, storage_loader: Any, *args: Any, **kwargs: Any
) -> pd.DataFrame:
    """Async version: Load from Neo4j first, fallback to storage."""
    if df := _try_neo4j_load(name):
        logger.debug(f"Loaded {name} from Neo4j ({len(df)} rows)")
        return df
    logger.debug(f"Loading {name} from storage")
    if asyncio.iscoroutinefunction(storage_loader):
        return await storage_loader(*args, **kwargs)
    return storage_loader(*args, **kwargs) if callable(storage_loader) else storage_loader
