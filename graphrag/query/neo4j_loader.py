# Copyright (c) 2024 Microsoft Corporation.
# Licensed under the MIT License

"""Neo4j data loader for query operations."""

import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

from graphrag.graphrag.graph.neo4j_client import (
    load_communities_from_neo4j,
    load_community_reports_from_neo4j,
    load_documents_from_neo4j,
    load_entities_from_neo4j,
    load_relationships_from_neo4j,
    load_text_units_from_neo4j,
)

NEO4J_LOADERS = {
    "entities": load_entities_from_neo4j,
    "communities": load_communities_from_neo4j,
    "community_reports": load_community_reports_from_neo4j,
    "relationships": load_relationships_from_neo4j,
    "text_units": load_text_units_from_neo4j,
    "documents": load_documents_from_neo4j,
}


async def load_async_from_neo4j(name: str) -> pd.DataFrame:
    """Load data from Neo4j."""
    if name not in NEO4J_LOADERS:
        logger.warning(f"Unknown table name: {name}")
        return pd.DataFrame()
    
    try:
        df = NEO4J_LOADERS[name]()
        logger.debug(f"Loaded {name} from Neo4j ({len(df)} rows)")
        return df
    except Exception as e:
        logger.error(f"Failed to load {name} from Neo4j: {e}")
        return pd.DataFrame()
