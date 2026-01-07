# Copyright (c) 2024 Microsoft Corporation.
# Licensed under the MIT License

"""
Experimental Neo4j client for GraphRAG.

This is a minimal proof of concept to replace 1-2 dataframe-based READ operations
during query time with Neo4j-backed reads. All Neo4j logic is optional and falls
back to existing dataframe logic if Neo4j is unavailable or disabled.

EXPERIMENTAL: This module provides Neo4j integration for GraphRAG.
All functionality is feature-flagged via GRAPHRAG_USE_NEO4J environment variable.
"""

import logging
import os
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# Try to import Neo4j driver, but make it optional
try:
    from neo4j import GraphDatabase
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    logger.warning(
        "Neo4j driver not available. Install with: pip install neo4j"
    )


def _is_neo4j_enabled() -> bool:
    """Check if Neo4j is enabled via environment variable."""
    return os.getenv("GRAPHRAG_USE_NEO4J", "false").lower() == "true"


def _get_neo4j_connection():
    """Get Neo4j database connection."""
    if not NEO4J_AVAILABLE or not _is_neo4j_enabled():
        return None
    
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")
    
    if not all([uri, user, password]):
        logger.warning(
            "Neo4j is enabled but connection details are missing. "
            "Set NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD environment variables."
        )
        return None
    
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        # Test connection
        driver.verify_connectivity()
        return driver
    except Exception as e:
        logger.warning(f"Failed to connect to Neo4j: {e}. Falling back to dataframe reads.")
        return None


def _get_neo4j_driver():
    """Get Neo4j driver instance (reusable)."""
    if not NEO4J_AVAILABLE or not _is_neo4j_enabled():
        return None
    
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")
    
    if not all([uri, user, password]):
        return None
    
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
        return driver
    except Exception as e:
        logger.warning(f"Failed to connect to Neo4j: {e}")
        return None


def get_entity_by_name_neo4j(entity_name: str) -> dict[str, Any] | None:
    """
    EXPERIMENTAL: Get entity by name from Neo4j.
    
    Falls back to None if Neo4j is unavailable, allowing caller to use dataframe logic.
    
    Parameters
    ----------
    entity_name : str
        Name of the entity to lookup
        
    Returns
    -------
    dict | None
        Entity data as dict with keys: id, name, type
        Returns None if Neo4j is unavailable or entity not found
    """
    driver = _get_neo4j_connection()
    if driver is None:
        return None
    
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (e:Entity {name: $name}) RETURN e.id as id, e.name as name, e.type as type LIMIT 1",
                name=entity_name
            )
            record = result.single()
            if record:
                return {
                    "id": record["id"],
                    "name": record["name"],
                    "type": record["type"]
                }
            return None
    except Exception as e:
        logger.warning(f"Error querying Neo4j for entity {entity_name}: {e}")
        return None
    finally:
        if driver is not None:
            driver.close()


def get_documents_by_entity_neo4j(entity_name: str) -> list[dict[str, Any]]:
    """
    EXPERIMENTAL: Get documents that mention an entity from Neo4j.
    
    Falls back to empty list if Neo4j is unavailable, allowing caller to use dataframe logic.
    
    Parameters
    ----------
    entity_name : str
        Name of the entity
        
    Returns
    -------
    list[dict]
        List of document dicts with keys: id, title, source
        Returns empty list if Neo4j is unavailable
    """
    driver = _get_neo4j_connection()
    if driver is None:
        return []
    
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (d:Document)-[:MENTIONS]->(e:Entity {name: $name}) "
                "RETURN d.id as id, d.text as text, d.source as source",
                name=entity_name
            )
            documents = []
            for record in result:
                documents.append({
                    "id": record["id"],
                    "text": record.get("text", ""),
                    "source": record.get("source", ""),
                    "title": record.get("source", "")  # Alias for compatibility
                })
            return documents
    except Exception as e:
        logger.warning(f"Error querying Neo4j for documents mentioning {entity_name}: {e}")
        return []
    finally:
        if driver is not None:
            driver.close()


# ============================================================================
# EXPERIMENTAL: Neo4j Write Functions
# ============================================================================

def write_documents_to_neo4j(documents: pd.DataFrame) -> bool:
    """
    EXPERIMENTAL: Write documents to Neo4j.
    
    Writes documents using the minimal schema:
    - (:Document {id, text, source})
    
    Parameters
    ----------
    documents : pd.DataFrame
        DataFrame with columns: id, text, title (used as source)
        
    Returns
    -------
    bool
        True if successful, False otherwise
    """
    if not _is_neo4j_enabled():
        return False
    
    driver = _get_neo4j_driver()
    if driver is None:
        return False
    
    try:
        with driver.session() as session:
            # Create constraint/index for Document.id
            session.run("CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE")
            
            # Batch write documents
            for _, row in documents.iterrows():
                doc_id = str(row.get("id", ""))
                text = str(row.get("text", ""))
                source = str(row.get("title", ""))  # Use title as source
                
                if not doc_id:
                    continue
                
                session.run(
                    "MERGE (d:Document {id: $id}) SET d.text = $text, d.source = $source",
                    id=doc_id,
                    text=text,
                    source=source
                )
            
            logger.info(f"Wrote {len(documents)} documents to Neo4j")
            return True
    except Exception as e:
        logger.warning(f"Error writing documents to Neo4j: {e}")
        return False
    finally:
        if driver is not None:
            driver.close()


def write_entities_to_neo4j(entities: pd.DataFrame) -> bool:
    """
    EXPERIMENTAL: Write entities to Neo4j.
    
    Writes entities using the minimal schema:
    - (:Entity {id, name, type})
    
    Parameters
    ----------
    entities : pd.DataFrame
        DataFrame with columns: id, title (used as name), type
        
    Returns
    -------
    bool
        True if successful, False otherwise
    """
    if not _is_neo4j_enabled():
        return False
    
    driver = _get_neo4j_driver()
    if driver is None:
        return False
    
    try:
        with driver.session() as session:
            # Create constraint/index for Entity.id
            session.run("CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE")
            
            # Batch write entities
            for _, row in entities.iterrows():
                entity_id = str(row.get("id", ""))
                name = str(row.get("title", ""))  # Entity.title is the name
                entity_type = str(row.get("type", "")) if pd.notna(row.get("type")) else ""
                
                if not entity_id or not name:
                    continue
                
                session.run(
                    "MERGE (e:Entity {id: $id}) SET e.name = $name, e.type = $type",
                    id=entity_id,
                    name=name,
                    type=entity_type
                )
            
            logger.info(f"Wrote {len(entities)} entities to Neo4j")
            return True
    except Exception as e:
        logger.warning(f"Error writing entities to Neo4j: {e}")
        return False
    finally:
        if driver is not None:
            driver.close()


def write_mentions_to_neo4j(
    entities: pd.DataFrame,
    documents: pd.DataFrame,
    text_units: pd.DataFrame | None = None
) -> bool:
    """
    EXPERIMENTAL: Write MENTIONS relationships between documents and entities.
    
    Creates relationships: (:Document)-[:MENTIONS]->(:Entity)
    
    The relationship is derived from:
    - Entities have text_unit_ids (list of text unit IDs where they appear)
    - Text units have document_ids (list of document IDs they belong to)
    - OR documents have text_unit_ids (list of text unit IDs in the document)
    
    Parameters
    ----------
    entities : pd.DataFrame
        DataFrame with columns: id, text_unit_ids
    documents : pd.DataFrame
        DataFrame with columns: id, text_unit_ids
    text_units : pd.DataFrame, optional
        DataFrame with columns: id, document_ids (if available)
        
    Returns
    -------
    bool
        True if successful, False otherwise
    """
    if not _is_neo4j_enabled():
        return False
    
    driver = _get_neo4j_driver()
    if driver is None:
        return False
    
    try:
        with driver.session() as session:
            mentions_count = 0
            
            # Build mapping: text_unit_id -> document_ids
            text_unit_to_docs = {}
            
            if text_units is not None and "document_ids" in text_units.columns:
                # Use text_units -> documents mapping
                for _, row in text_units.iterrows():
                    text_unit_id = str(row.get("id", ""))
                    doc_ids = row.get("document_ids", [])
                    if text_unit_id and isinstance(doc_ids, list):
                        text_unit_to_docs[text_unit_id] = doc_ids
            else:
                # Use documents -> text_units mapping (reverse)
                for _, doc_row in documents.iterrows():
                    doc_id = str(doc_row.get("id", ""))
                    text_unit_ids = doc_row.get("text_unit_ids", [])
                    if doc_id and isinstance(text_unit_ids, list):
                        for text_unit_id in text_unit_ids:
                            if text_unit_id not in text_unit_to_docs:
                                text_unit_to_docs[str(text_unit_id)] = []
                            text_unit_to_docs[str(text_unit_id)].append(doc_id)
            
            # For each entity, find documents via text_unit_ids
            for _, entity_row in entities.iterrows():
                entity_id = str(entity_row.get("id", ""))
                text_unit_ids = entity_row.get("text_unit_ids", [])
                
                if not entity_id or not isinstance(text_unit_ids, list):
                    continue
                
                # Find all documents that contain text units where this entity appears
                doc_ids_set = set()
                for text_unit_id in text_unit_ids:
                    text_unit_id_str = str(text_unit_id)
                    if text_unit_id_str in text_unit_to_docs:
                        doc_ids_set.update(text_unit_to_docs[text_unit_id_str])
                
                # Create MENTIONS relationships
                for doc_id in doc_ids_set:
                    session.run(
                        "MATCH (d:Document {id: $doc_id}), (e:Entity {id: $entity_id}) "
                        "MERGE (d)-[:MENTIONS]->(e)",
                        doc_id=str(doc_id),
                        entity_id=entity_id
                    )
                    mentions_count += 1
            
            logger.info(f"Created {mentions_count} MENTIONS relationships in Neo4j")
            return True
    except Exception as e:
        logger.warning(f"Error writing mentions to Neo4j: {e}")
        return False
    finally:
        if driver is not None:
            driver.close()


# ============================================================================
# EXPERIMENTAL: Cypher Query Utility
# ============================================================================

def run_cypher(query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """
    EXPERIMENTAL: Run an arbitrary Cypher query against Neo4j.
    
    This utility function is intended for exploration and notebook use only.
    Do NOT expose this via an API or server.
    
    Parameters
    ----------
    query : str
        Cypher query string
    params : dict, optional
        Query parameters
        
    Returns
    -------
    list[dict]
        List of result records as dictionaries
        Returns empty list if Neo4j is unavailable or query fails
    """
    if not _is_neo4j_enabled():
        logger.warning("Neo4j is not enabled. Set GRAPHRAG_USE_NEO4J=true")
        return []
    
    driver = _get_neo4j_driver()
    if driver is None:
        return []
    
    try:
        with driver.session() as session:
            result = session.run(query, params or {})
            records = []
            for record in result:
                records.append(dict(record))
            return records
    except Exception as e:
        logger.warning(f"Error running Cypher query: {e}")
        return []

