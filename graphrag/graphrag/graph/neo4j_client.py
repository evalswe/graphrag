# Copyright (c) 2024 Microsoft Corporation.
# Licensed under the MIT License

"""
Experimental Neo4j client for GraphRAG using Cypher queries.

This module provides Neo4j integration for GraphRAG using Cypher/GQL directly.
It replaces dataframe-based READ operations during query time with Neo4j-backed reads.
All Neo4j logic is optional and falls back to existing dataframe logic if Neo4j is 
unavailable or disabled.

EXPERIMENTAL: This module provides Neo4j integration for GraphRAG.
All functionality is feature-flagged via GRAPHRAG_USE_NEO4J environment variable.

Uses Cypher queries directly - no GraphQL or server components.
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


def write_communities_to_neo4j(communities: pd.DataFrame) -> bool:
    """
    EXPERIMENTAL: Write communities to Neo4j.
    
    Writes communities using the schema:
    - (:Community {id, community, level, parent, children, title, entity_ids, relationship_ids, text_unit_ids, period, size})
    
    Parameters
    ----------
    communities : pd.DataFrame
        DataFrame with columns: id, community, level, parent, children, title, entity_ids, relationship_ids, text_unit_ids, period, size
        
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
            # Create constraint/index for Community.id
            session.run("CREATE CONSTRAINT community_id IF NOT EXISTS FOR (c:Community) REQUIRE c.id IS UNIQUE")
            
            # Batch write communities
            for _, row in communities.iterrows():
                community_id = str(row.get("id", ""))
                community_num = row.get("community", None)
                level = row.get("level", None)
                parent = row.get("parent", None)
                children = row.get("children", []) if isinstance(row.get("children"), list) else []
                title = str(row.get("title", "")) if pd.notna(row.get("title")) else ""
                entity_ids = row.get("entity_ids", []) if isinstance(row.get("entity_ids"), list) else []
                relationship_ids = row.get("relationship_ids", []) if isinstance(row.get("relationship_ids"), list) else []
                text_unit_ids = row.get("text_unit_ids", []) if isinstance(row.get("text_unit_ids"), list) else []
                period = str(row.get("period", "")) if pd.notna(row.get("period")) else ""
                size = row.get("size", None)
                
                if not community_id:
                    continue
                
                session.run(
                    "MERGE (c:Community {id: $id}) "
                    "SET c.community = $community, c.level = $level, c.parent = $parent, "
                    "c.children = $children, c.title = $title, c.entity_ids = $entity_ids, "
                    "c.relationship_ids = $relationship_ids, c.text_unit_ids = $text_unit_ids, "
                    "c.period = $period, c.size = $size",
                    id=community_id,
                    community=community_num,
                    level=level,
                    parent=parent,
                    children=children,
                    title=title,
                    entity_ids=entity_ids,
                    relationship_ids=relationship_ids,
                    text_unit_ids=text_unit_ids,
                    period=period,
                    size=size
                )
            
            logger.info(f"Wrote {len(communities)} communities to Neo4j")
            return True
    except Exception as e:
        logger.warning(f"Error writing communities to Neo4j: {e}")
        return False
    finally:
        if driver is not None:
            driver.close()


def write_community_reports_to_neo4j(community_reports: pd.DataFrame) -> bool:
    """
    EXPERIMENTAL: Write community reports to Neo4j.
    
    Writes community reports using the schema:
    - (:CommunityReport {id, community, level, parent, children, title, summary, full_content, rank, rating_explanation, findings, full_content_json, period, size})
    
    Parameters
    ----------
    community_reports : pd.DataFrame
        DataFrame with columns: id, community, level, parent, children, title, summary, full_content, rank, rating_explanation, findings, full_content_json, period, size
        
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
            # Create constraint/index for CommunityReport.id
            session.run("CREATE CONSTRAINT community_report_id IF NOT EXISTS FOR (cr:CommunityReport) REQUIRE cr.id IS UNIQUE")
            
            # Batch write community reports
            for _, row in community_reports.iterrows():
                report_id = str(row.get("id", ""))
                community_num = row.get("community", None)
                level = row.get("level", None)
                parent = row.get("parent", None)
                children = row.get("children", []) if isinstance(row.get("children"), list) else []
                title = str(row.get("title", "")) if pd.notna(row.get("title")) else ""
                summary = str(row.get("summary", "")) if pd.notna(row.get("summary")) else ""
                full_content = str(row.get("full_content", "")) if pd.notna(row.get("full_content")) else ""
                rank = row.get("rank", None)
                rating_explanation = str(row.get("rating_explanation", "")) if pd.notna(row.get("rating_explanation")) else ""
                findings = row.get("findings", None)  # Can be dict/JSON
                full_content_json = row.get("full_content_json", None)  # Can be dict/JSON
                period = str(row.get("period", "")) if pd.notna(row.get("period")) else ""
                size = row.get("size", None)
                
                if not report_id:
                    continue
                
                session.run(
                    "MERGE (cr:CommunityReport {id: $id}) "
                    "SET cr.community = $community, cr.level = $level, cr.parent = $parent, "
                    "cr.children = $children, cr.title = $title, cr.summary = $summary, "
                    "cr.full_content = $full_content, cr.rank = $rank, cr.rating_explanation = $rating_explanation, "
                    "cr.findings = $findings, cr.full_content_json = $full_content_json, "
                    "cr.period = $period, cr.size = $size",
                    id=report_id,
                    community=community_num,
                    level=level,
                    parent=parent,
                    children=children,
                    title=title,
                    summary=summary,
                    full_content=full_content,
                    rank=rank,
                    rating_explanation=rating_explanation,
                    findings=findings,
                    full_content_json=full_content_json,
                    period=period,
                    size=size
                )
            
            logger.info(f"Wrote {len(community_reports)} community reports to Neo4j")
            return True
    except Exception as e:
        logger.warning(f"Error writing community reports to Neo4j: {e}")
        return False
    finally:
        if driver is not None:
            driver.close()


def write_relationships_to_neo4j(relationships: pd.DataFrame) -> bool:
    """
    EXPERIMENTAL: Write relationships to Neo4j.
    
    Writes relationships using the schema:
    - (:Relationship {id, source, target, description, weight, degree, text_unit_ids})
    - Creates relationships: (:Entity {name: source})-[:RELATES_TO]->(:Entity {name: target})
    
    Parameters
    ----------
    relationships : pd.DataFrame
        DataFrame with columns: id, source, target, description, weight, degree, text_unit_ids
        
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
            # Create constraint/index for Relationship.id
            session.run("CREATE CONSTRAINT relationship_id IF NOT EXISTS FOR (r:Relationship) REQUIRE r.id IS UNIQUE")
            
            # Batch write relationships
            for _, row in relationships.iterrows():
                rel_id = str(row.get("id", ""))
                source = str(row.get("source", "")) if pd.notna(row.get("source")) else ""
                target = str(row.get("target", "")) if pd.notna(row.get("target")) else ""
                description = str(row.get("description", "")) if pd.notna(row.get("description")) else ""
                weight = row.get("weight", None)
                degree = row.get("degree", None)
                text_unit_ids = row.get("text_unit_ids", []) if isinstance(row.get("text_unit_ids"), list) else []
                
                if not rel_id or not source or not target:
                    continue
                
                # Create relationship node
                session.run(
                    "MERGE (r:Relationship {id: $id}) "
                    "SET r.source = $source, r.target = $target, r.description = $description, "
                    "r.weight = $weight, r.degree = $degree, r.text_unit_ids = $text_unit_ids",
                    id=rel_id,
                    source=source,
                    target=target,
                    description=description,
                    weight=weight,
                    degree=degree,
                    text_unit_ids=text_unit_ids
                )
                
                # Create RELATES_TO relationship between entities
                session.run(
                    "MATCH (e1:Entity {name: $source}), (e2:Entity {name: $target}) "
                    "MERGE (e1)-[r:RELATES_TO {id: $rel_id}]->(e2) "
                    "SET r.description = $description, r.weight = $weight",
                    source=source,
                    target=target,
                    rel_id=rel_id,
                    description=description,
                    weight=weight
                )
            
            logger.info(f"Wrote {len(relationships)} relationships to Neo4j")
            return True
    except Exception as e:
        logger.warning(f"Error writing relationships to Neo4j: {e}")
        return False
    finally:
        if driver is not None:
            driver.close()


def write_text_units_to_neo4j(text_units: pd.DataFrame) -> bool:
    """
    EXPERIMENTAL: Write text units to Neo4j.
    
    Writes text units using the schema:
    - (:TextUnit {id, text, n_tokens, document_ids, entity_ids, relationship_ids, covariate_ids})
    
    Parameters
    ----------
    text_units : pd.DataFrame
        DataFrame with columns: id, text, n_tokens, document_ids, entity_ids, relationship_ids, covariate_ids
        
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
            # Create constraint/index for TextUnit.id
            session.run("CREATE CONSTRAINT text_unit_id IF NOT EXISTS FOR (tu:TextUnit) REQUIRE tu.id IS UNIQUE")
            
            # Batch write text units
            for _, row in text_units.iterrows():
                text_unit_id = str(row.get("id", ""))
                text = str(row.get("text", "")) if pd.notna(row.get("text")) else ""
                n_tokens = row.get("n_tokens", None)
                document_ids = row.get("document_ids", []) if isinstance(row.get("document_ids"), list) else []
                entity_ids = row.get("entity_ids", []) if isinstance(row.get("entity_ids"), list) else []
                relationship_ids = row.get("relationship_ids", []) if isinstance(row.get("relationship_ids"), list) else []
                covariate_ids = row.get("covariate_ids", []) if isinstance(row.get("covariate_ids"), list) else []
                
                if not text_unit_id:
                    continue
                
                session.run(
                    "MERGE (tu:TextUnit {id: $id}) "
                    "SET tu.text = $text, tu.n_tokens = $n_tokens, tu.document_ids = $document_ids, "
                    "tu.entity_ids = $entity_ids, tu.relationship_ids = $relationship_ids, "
                    "tu.covariate_ids = $covariate_ids",
                    id=text_unit_id,
                    text=text,
                    n_tokens=n_tokens,
                    document_ids=document_ids,
                    entity_ids=entity_ids,
                    relationship_ids=relationship_ids,
                    covariate_ids=covariate_ids
                )
            
            logger.info(f"Wrote {len(text_units)} text units to Neo4j")
            return True
    except Exception as e:
        logger.warning(f"Error writing text units to Neo4j: {e}")
        return False
    finally:
        if driver is not None:
            driver.close()


# ============================================================================
# EXPERIMENTAL: Neo4j Read Functions (Load from Neo4j instead of Parquet)
# ============================================================================

def load_entities_from_neo4j() -> pd.DataFrame:
    """
    EXPERIMENTAL: Load entities from Neo4j.
    
    Returns
    -------
    pd.DataFrame
        DataFrame with entities, or empty DataFrame if Neo4j unavailable
    """
    if not _is_neo4j_enabled():
        return pd.DataFrame()
    
    driver = _get_neo4j_driver()
    if driver is None:
        return pd.DataFrame()
    
    try:
        with driver.session() as session:
            result = session.run("MATCH (e:Entity) RETURN e.id as id, e.name as title, e.type as type")
            records = []
            for record in result:
                records.append({
                    "id": record["id"],
                    "title": record.get("title", ""),
                    "type": record.get("type", "")
                })
            return pd.DataFrame(records)
    except Exception as e:
        logger.warning(f"Error loading entities from Neo4j: {e}")
        return pd.DataFrame()
    finally:
        if driver is not None:
            driver.close()


def load_communities_from_neo4j() -> pd.DataFrame:
    """
    EXPERIMENTAL: Load communities from Neo4j.
    
    Returns
    -------
    pd.DataFrame
        DataFrame with communities, or empty DataFrame if Neo4j unavailable
    """
    if not _is_neo4j_enabled():
        return pd.DataFrame()
    
    driver = _get_neo4j_driver()
    if driver is None:
        return pd.DataFrame()
    
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (c:Community) "
                "RETURN c.id as id, c.community as community, c.level as level, "
                "c.parent as parent, c.children as children, c.title as title, "
                "c.entity_ids as entity_ids, c.relationship_ids as relationship_ids, "
                "c.text_unit_ids as text_unit_ids, c.period as period, c.size as size"
            )
            records = []
            for record in result:
                records.append({
                    "id": record["id"],
                    "community": record.get("community"),
                    "level": record.get("level"),
                    "parent": record.get("parent"),
                    "children": record.get("children", []),
                    "title": record.get("title", ""),
                    "entity_ids": record.get("entity_ids", []),
                    "relationship_ids": record.get("relationship_ids", []),
                    "text_unit_ids": record.get("text_unit_ids", []),
                    "period": record.get("period", ""),
                    "size": record.get("size")
                })
            return pd.DataFrame(records)
    except Exception as e:
        logger.warning(f"Error loading communities from Neo4j: {e}")
        return pd.DataFrame()
    finally:
        if driver is not None:
            driver.close()


def load_community_reports_from_neo4j() -> pd.DataFrame:
    """
    EXPERIMENTAL: Load community reports from Neo4j.
    
    Returns
    -------
    pd.DataFrame
        DataFrame with community reports, or empty DataFrame if Neo4j unavailable
    """
    if not _is_neo4j_enabled():
        return pd.DataFrame()
    
    driver = _get_neo4j_driver()
    if driver is None:
        return pd.DataFrame()
    
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (cr:CommunityReport) "
                "RETURN cr.id as id, cr.community as community, cr.level as level, "
                "cr.parent as parent, cr.children as children, cr.title as title, "
                "cr.summary as summary, cr.full_content as full_content, cr.rank as rank, "
                "cr.rating_explanation as rating_explanation, cr.findings as findings, "
                "cr.full_content_json as full_content_json, cr.period as period, cr.size as size"
            )
            records = []
            for record in result:
                records.append({
                    "id": record["id"],
                    "community": record.get("community"),
                    "level": record.get("level"),
                    "parent": record.get("parent"),
                    "children": record.get("children", []),
                    "title": record.get("title", ""),
                    "summary": record.get("summary", ""),
                    "full_content": record.get("full_content", ""),
                    "rank": record.get("rank"),
                    "rating_explanation": record.get("rating_explanation", ""),
                    "findings": record.get("findings"),
                    "full_content_json": record.get("full_content_json"),
                    "period": record.get("period", ""),
                    "size": record.get("size")
                })
            return pd.DataFrame(records)
    except Exception as e:
        logger.warning(f"Error loading community reports from Neo4j: {e}")
        return pd.DataFrame()
    finally:
        if driver is not None:
            driver.close()


def load_relationships_from_neo4j() -> pd.DataFrame:
    """
    EXPERIMENTAL: Load relationships from Neo4j.
    
    Returns
    -------
    pd.DataFrame
        DataFrame with relationships, or empty DataFrame if Neo4j unavailable
    """
    if not _is_neo4j_enabled():
        return pd.DataFrame()
    
    driver = _get_neo4j_driver()
    if driver is None:
        return pd.DataFrame()
    
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (r:Relationship) "
                "RETURN r.id as id, r.source as source, r.target as target, "
                "r.description as description, r.weight as weight, r.degree as degree, "
                "r.text_unit_ids as text_unit_ids"
            )
            records = []
            for record in result:
                records.append({
                    "id": record["id"],
                    "source": record.get("source", ""),
                    "target": record.get("target", ""),
                    "description": record.get("description", ""),
                    "weight": record.get("weight"),
                    "degree": record.get("degree"),
                    "text_unit_ids": record.get("text_unit_ids", [])
                })
            return pd.DataFrame(records)
    except Exception as e:
        logger.warning(f"Error loading relationships from Neo4j: {e}")
        return pd.DataFrame()
    finally:
        if driver is not None:
            driver.close()


def load_text_units_from_neo4j() -> pd.DataFrame:
    """
    EXPERIMENTAL: Load text units from Neo4j.
    
    Returns
    -------
    pd.DataFrame
        DataFrame with text units, or empty DataFrame if Neo4j unavailable
    """
    if not _is_neo4j_enabled():
        return pd.DataFrame()
    
    driver = _get_neo4j_driver()
    if driver is None:
        return pd.DataFrame()
    
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (tu:TextUnit) "
                "RETURN tu.id as id, tu.text as text, tu.n_tokens as n_tokens, "
                "tu.document_ids as document_ids, tu.entity_ids as entity_ids, "
                "tu.relationship_ids as relationship_ids, tu.covariate_ids as covariate_ids"
            )
            records = []
            for record in result:
                records.append({
                    "id": record["id"],
                    "text": record.get("text", ""),
                    "n_tokens": record.get("n_tokens"),
                    "document_ids": record.get("document_ids", []),
                    "entity_ids": record.get("entity_ids", []),
                    "relationship_ids": record.get("relationship_ids", []),
                    "covariate_ids": record.get("covariate_ids", [])
                })
            return pd.DataFrame(records)
    except Exception as e:
        logger.warning(f"Error loading text units from Neo4j: {e}")
        return pd.DataFrame()
    finally:
        if driver is not None:
            driver.close()


def load_documents_from_neo4j() -> pd.DataFrame:
    """
    EXPERIMENTAL: Load documents from Neo4j.
    
    Returns
    -------
    pd.DataFrame
        DataFrame with documents, or empty DataFrame if Neo4j unavailable
    """
    if not _is_neo4j_enabled():
        return pd.DataFrame()
    
    driver = _get_neo4j_driver()
    if driver is None:
        return pd.DataFrame()
    
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (d:Document) "
                "RETURN d.id as id, d.text as text, d.source as source"
            )
            records = []
            for record in result:
                records.append({
                    "id": record["id"],
                    "text": record.get("text", ""),
                    "title": record.get("source", ""),  # Use source as title for compatibility
                    "source": record.get("source", "")
                })
            return pd.DataFrame(records)
    except Exception as e:
        logger.warning(f"Error loading documents from Neo4j: {e}")
        return pd.DataFrame()
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

