# Copyright (c) 2024 Microsoft Corporation.
# Licensed under the MIT License

"""Cypher Query API for GraphRAG - Execute arbitrary Cypher queries against Neo4j."""

import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    from graphrag.graphrag.graph.neo4j_client import run_cypher
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False


def query_cypher(query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Execute an arbitrary Cypher query against Neo4j."""
    if not NEO4J_AVAILABLE:
        logger.warning("Neo4j not available. Install with: pip install neo4j")
        return []
    return run_cypher(query, params)


def generate_cypher(query: str, config: Any | None = None, model_id: str | None = None) -> str:
    """Generate Cypher query from natural language using LLM (framework ready)."""
    if config is None:
        logger.warning("No config provided. Returning template.")
        return f"// Generated query for: {query}\nMATCH (e:Entity) RETURN e LIMIT 10"
    # TODO: Implement LLM-powered Cypher generation
    logger.info("LLM-powered Cypher generation not yet implemented.")
    return f"// Generated query for: {query}\nMATCH (e:Entity) RETURN e LIMIT 10"


def get_cypher_schema() -> dict[str, Any]:
    """Get Neo4j schema information for query generation."""
    if not NEO4J_AVAILABLE:
        return {"node_labels": [], "relationship_types": [], "properties": {}}
    
    try:
        results = run_cypher("CALL db.schema.visualization() YIELD nodes, relationships RETURN nodes, relationships")
        if results:
            return {
                "node_labels": ["Entity", "Document", "TextUnit", "Community", "CommunityReport", "Relationship"],
                "relationship_types": ["MENTIONS", "RELATES_TO"],
                "properties": {
                    "Entity": ["id", "name", "type", "description"],
                    "Document": ["id", "text", "source", "title"],
                    "TextUnit": ["id", "text", "n_tokens", "document_ids", "entity_ids"],
                    "Community": ["id", "community", "level", "title", "entity_ids"],
                    "Relationship": ["id", "source", "target", "description", "weight"],
                }
            }
    except Exception as e:
        logger.warning(f"Failed to get schema: {e}")
    
    # Return default schema
    return {
        "node_labels": ["Entity", "Document", "TextUnit", "Community", "CommunityReport", "Relationship"],
        "relationship_types": ["MENTIONS", "RELATES_TO"],
        "properties": {
            "Entity": ["id", "name", "type", "description"],
            "Document": ["id", "text", "source", "title"],
            "TextUnit": ["id", "text", "n_tokens", "document_ids", "entity_ids"],
            "Community": ["id", "community", "level", "title", "entity_ids"],
            "Relationship": ["id", "source", "target", "description", "weight"],
        }
    }
