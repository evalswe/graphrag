# Copyright (c) 2024 Microsoft Corporation.
# Licensed under the MIT License

"""Neo4j client for GraphRAG using Cypher queries."""

import logging
import os
from typing import Any

import pandas as pd
from neo4j import GraphDatabase

logger = logging.getLogger(__name__)


def _is_neo4j_enabled() -> bool:
    """Check if Neo4j is enabled via environment variable."""
    return os.getenv("GRAPHRAG_USE_NEO4J", "false").lower() == "true"


def _get_neo4j_connection():
    """Get Neo4j database connection."""
    if not _is_neo4j_enabled():
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
        logger.warning(f"Failed to connect to Neo4j: {e}")
        return None


def _get_neo4j_driver():
    """Get Neo4j driver instance (reusable)."""
    if not _is_neo4j_enabled():
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
    """Get entity by name from Neo4j."""
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


def get_entity_by_id_neo4j(entity_id: str) -> dict[str, Any] | None:
    """Get entity by ID from Neo4j."""
    driver = _get_neo4j_connection()
    if driver is None:
        return None
    
    try:
        with driver.session() as session:
            # Try with dashes first, then without
            result = session.run(
                "MATCH (e:Entity {id: $id}) RETURN e.id as id, e.name as name, e.type as type LIMIT 1",
                id=entity_id
            )
            record = result.single()
            if record:
                return {
                    "id": record["id"],
                    "name": record["name"],
                    "type": record["type"]
                }
            # Try without dashes if entity_id contains dashes
            if "-" in entity_id:
                result = session.run(
                    "MATCH (e:Entity {id: $id}) RETURN e.id as id, e.name as name, e.type as type LIMIT 1",
                    id=entity_id.replace("-", "")
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
        logger.warning(f"Error querying Neo4j for entity ID {entity_id}: {e}")
        return None
    finally:
        if driver is not None:
            driver.close()


def get_connected_entities_neo4j(
    entity_name: str,
    exclude_entity_names: list[str] | None = None,
    k: int | None = None,
) -> list[dict[str, Any]]:
    """Get entities connected to the target entity via RELATES_TO relationships, sorted by rank."""
    driver = _get_neo4j_connection()
    if driver is None:
        return []
    
    if exclude_entity_names is None:
        exclude_entity_names = []
    
    try:
        with driver.session() as session:
            # Find entities connected via RELATES_TO relationships (both directions)
            # Count relationships as a proxy for rank
            query = (
                "MATCH (e1:Entity {name: $entity_name})-[r:RELATES_TO]-(e2:Entity) "
                "WHERE e2.name NOT IN $exclude_names "
                "WITH e2, count(r) as rel_count "
                "RETURN DISTINCT e2.id as id, e2.name as name, e2.type as type, rel_count as rank "
                "ORDER BY rel_count DESC"
            )
            if k:
                query += f" LIMIT {k}"
            
            result = session.run(
                query,
                entity_name=entity_name,
                exclude_names=exclude_entity_names or []
            )
            records = []
            for record in result:
                records.append({
                    "id": record["id"],
                    "name": record["name"],
                    "type": record.get("type"),
                    "rank": record.get("rank")
                })
            return records
    except Exception as e:
        logger.warning(f"Error querying Neo4j for connected entities to {entity_name}: {e}")
        return []
    finally:
        if driver is not None:
            driver.close()


def get_documents_by_entity_neo4j(entity_name: str) -> list[dict[str, Any]]:
    """Get documents that mention an entity from Neo4j."""
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


def write_documents_to_neo4j(documents: pd.DataFrame) -> bool:
    """Write documents to Neo4j."""
    if not _is_neo4j_enabled():
        return False
    
    driver = _get_neo4j_driver()
    if driver is None:
        return False
    
    try:
        with driver.session() as session:
            # Create constraint/index for Document.id
            session.run("CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE")
            
            # Prepare batch data (iterrows is only for data preparation, not writing)
            batch_data = []
            for _, row in documents.iterrows():
                doc_id = str(row.get("id", ""))
                if not doc_id:
                    continue
                batch_data.append({
                    "id": doc_id,
                    "text": str(row.get("text", "")),
                    "source": str(row.get("title", ""))  # Use title as source
                })
            
            # Batch write documents using UNWIND
            if batch_data:
                session.run(
                    "UNWIND $rows AS row "
                    "MERGE (d:Document {id: row.id}) "
                    "SET d.text = row.text, d.source = row.source",
                    rows=batch_data
                )
            
            logger.info(f"Wrote {len(batch_data)} documents to Neo4j")
            return True
    except Exception as e:
        logger.warning(f"Error writing documents to Neo4j: {e}")
        return False
    finally:
        if driver is not None:
            driver.close()


def write_entities_to_neo4j(entities: pd.DataFrame) -> bool:
    """Write entities to Neo4j."""
    if not _is_neo4j_enabled():
        return False
    
    driver = _get_neo4j_driver()
    if driver is None:
        return False
    
    try:
        with driver.session() as session:
            # Create constraint/index for Entity.id
            session.run("CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE")
            
            # Prepare batch data (iterrows is only for data preparation, not writing)
            batch_data = []
            for _, row in entities.iterrows():
                entity_id = str(row.get("id", ""))
                name = str(row.get("title", ""))  # Entity.title is the name
                if not entity_id or not name:
                    continue
                batch_data.append({
                    "id": entity_id,
                    "name": name,
                    "type": str(row.get("type", "")) if pd.notna(row.get("type")) else ""
                })
            
            # Batch write entities using UNWIND
            if batch_data:
                session.run(
                    "UNWIND $rows AS row "
                    "MERGE (e:Entity {id: row.id}) "
                    "SET e.name = row.name, e.type = row.type",
                    rows=batch_data
                )
            
            logger.info(f"Wrote {len(batch_data)} entities to Neo4j")
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
    """Write MENTIONS relationships between documents and entities."""
    if not _is_neo4j_enabled():
        return False
    
    driver = _get_neo4j_driver()
    if driver is None:
        return False
    
    try:
        with driver.session() as session:
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
            
            # Build batch data for MENTIONS relationships
            batch_data = []
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
                
                # Add to batch
                for doc_id in doc_ids_set:
                    batch_data.append({
                        "doc_id": str(doc_id),
                        "entity_id": entity_id
                    })
            
            # Batch create MENTIONS relationships using UNWIND
            mentions_count = 0
            if batch_data:
                session.run(
                    "UNWIND $rows AS row "
                    "MATCH (d:Document {id: row.doc_id}), (e:Entity {id: row.entity_id}) "
                    "MERGE (d)-[:MENTIONS]->(e)",
                    rows=batch_data
                )
                mentions_count = len(batch_data)
            
            logger.info(f"Created {mentions_count} MENTIONS relationships in Neo4j")
            return True
    except Exception as e:
        logger.warning(f"Error writing mentions to Neo4j: {e}")
        return False
    finally:
        if driver is not None:
            driver.close()


def write_communities_to_neo4j(communities: pd.DataFrame) -> bool:
    """Write communities to Neo4j."""
    if not _is_neo4j_enabled():
        return False
    
    driver = _get_neo4j_driver()
    if driver is None:
        return False
    
    try:
        with driver.session() as session:
            # Create constraint/index for Community.id
            session.run("CREATE CONSTRAINT community_id IF NOT EXISTS FOR (c:Community) REQUIRE c.id IS UNIQUE")
            
            # Prepare batch data (iterrows is only for data preparation, not writing)
            batch_data = []
            for _, row in communities.iterrows():
                community_id = str(row.get("id", ""))
                if not community_id:
                    continue
                batch_data.append({
                    "id": community_id,
                    "community": row.get("community", None),
                    "level": row.get("level", None),
                    "parent": row.get("parent", None),
                    "children": row.get("children", []) if isinstance(row.get("children"), list) else [],
                    "title": str(row.get("title", "")) if pd.notna(row.get("title")) else "",
                    "entity_ids": row.get("entity_ids", []) if isinstance(row.get("entity_ids"), list) else [],
                    "relationship_ids": row.get("relationship_ids", []) if isinstance(row.get("relationship_ids"), list) else [],
                    "text_unit_ids": row.get("text_unit_ids", []) if isinstance(row.get("text_unit_ids"), list) else [],
                    "period": str(row.get("period", "")) if pd.notna(row.get("period")) else "",
                    "size": row.get("size", None)
                })
            
            # Batch write communities using UNWIND
            if batch_data:
                session.run(
                    "UNWIND $rows AS row "
                    "MERGE (c:Community {id: row.id}) "
                    "SET c.community = row.community, c.level = row.level, c.parent = row.parent, "
                    "c.children = row.children, c.title = row.title, c.entity_ids = row.entity_ids, "
                    "c.relationship_ids = row.relationship_ids, c.text_unit_ids = row.text_unit_ids, "
                    "c.period = row.period, c.size = row.size",
                    rows=batch_data
                )
            
            logger.info(f"Wrote {len(batch_data)} communities to Neo4j")
            return True
    except Exception as e:
        logger.warning(f"Error writing communities to Neo4j: {e}")
        return False
    finally:
        if driver is not None:
            driver.close()


def write_community_reports_to_neo4j(community_reports: pd.DataFrame) -> bool:
    """Write community reports to Neo4j."""
    if not _is_neo4j_enabled():
        return False
    
    driver = _get_neo4j_driver()
    if driver is None:
        return False
    
    try:
        with driver.session() as session:
            # Create constraint/index for CommunityReport.id
            session.run("CREATE CONSTRAINT community_report_id IF NOT EXISTS FOR (cr:CommunityReport) REQUIRE cr.id IS UNIQUE")
            
            # Prepare batch data (iterrows is only for data preparation, not writing)
            batch_data = []
            for _, row in community_reports.iterrows():
                report_id = str(row.get("id", ""))
                if not report_id:
                    continue
                batch_data.append({
                    "id": report_id,
                    "community": row.get("community", None),
                    "level": row.get("level", None),
                    "parent": row.get("parent", None),
                    "children": row.get("children", []) if isinstance(row.get("children"), list) else [],
                    "title": str(row.get("title", "")) if pd.notna(row.get("title")) else "",
                    "summary": str(row.get("summary", "")) if pd.notna(row.get("summary")) else "",
                    "full_content": str(row.get("full_content", "")) if pd.notna(row.get("full_content")) else "",
                    "rank": row.get("rank", None),
                    "rating_explanation": str(row.get("rating_explanation", "")) if pd.notna(row.get("rating_explanation")) else "",
                    "findings": row.get("findings", None),
                    "full_content_json": row.get("full_content_json", None),
                    "period": str(row.get("period", "")) if pd.notna(row.get("period")) else "",
                    "size": row.get("size", None)
                })
            
            # Batch write community reports using UNWIND
            if batch_data:
                session.run(
                    "UNWIND $rows AS row "
                    "MERGE (cr:CommunityReport {id: row.id}) "
                    "SET cr.community = row.community, cr.level = row.level, cr.parent = row.parent, "
                    "cr.children = row.children, cr.title = row.title, cr.summary = row.summary, "
                    "cr.full_content = row.full_content, cr.rank = row.rank, cr.rating_explanation = row.rating_explanation, "
                    "cr.findings = row.findings, cr.full_content_json = row.full_content_json, "
                    "cr.period = row.period, cr.size = row.size",
                    rows=batch_data
                )
            
            logger.info(f"Wrote {len(batch_data)} community reports to Neo4j")
            return True
    except Exception as e:
        logger.warning(f"Error writing community reports to Neo4j: {e}")
        return False
    finally:
        if driver is not None:
            driver.close()


def write_relationships_to_neo4j(relationships: pd.DataFrame) -> bool:
    """Write relationships to Neo4j."""
    if not _is_neo4j_enabled():
        return False
    
    driver = _get_neo4j_driver()
    if driver is None:
        return False
    
    try:
        with driver.session() as session:
            # Create constraint/index for Relationship.id
            session.run("CREATE CONSTRAINT relationship_id IF NOT EXISTS FOR (r:Relationship) REQUIRE r.id IS UNIQUE")
            
            # Prepare batch data (iterrows is only for data preparation, not writing)
            batch_data = []
            for _, row in relationships.iterrows():
                rel_id = str(row.get("id", ""))
                source = str(row.get("source", "")) if pd.notna(row.get("source")) else ""
                target = str(row.get("target", "")) if pd.notna(row.get("target")) else ""
                if not rel_id or not source or not target:
                    continue
                batch_data.append({
                    "id": rel_id,
                    "source": source,
                    "target": target,
                    "description": str(row.get("description", "")) if pd.notna(row.get("description")) else "",
                    "weight": row.get("weight", None),
                    "degree": row.get("degree", None),
                    "text_unit_ids": row.get("text_unit_ids", []) if isinstance(row.get("text_unit_ids"), list) else []
                })
            
            # Batch write relationship nodes using UNWIND
            if batch_data:
                session.run(
                    "UNWIND $rows AS row "
                    "MERGE (r:Relationship {id: row.id}) "
                    "SET r.source = row.source, r.target = row.target, r.description = row.description, "
                    "r.weight = row.weight, r.degree = row.degree, r.text_unit_ids = row.text_unit_ids",
                    rows=batch_data
                )
                
                # Batch create RELATES_TO relationships between entities
                session.run(
                    "UNWIND $rows AS row "
                    "MATCH (e1:Entity {name: row.source}), (e2:Entity {name: row.target}) "
                    "MERGE (e1)-[r:RELATES_TO {id: row.id}]->(e2) "
                    "SET r.description = row.description, r.weight = row.weight",
                    rows=batch_data
                )
            
            logger.info(f"Wrote {len(batch_data)} relationships to Neo4j")
            return True
    except Exception as e:
        logger.warning(f"Error writing relationships to Neo4j: {e}")
        return False
    finally:
        if driver is not None:
            driver.close()


def write_text_units_to_neo4j(text_units: pd.DataFrame) -> bool:
    """Write text units to Neo4j."""
    if not _is_neo4j_enabled():
        return False
    
    driver = _get_neo4j_driver()
    if driver is None:
        return False
    
    try:
        with driver.session() as session:
            # Create constraint/index for TextUnit.id
            session.run("CREATE CONSTRAINT text_unit_id IF NOT EXISTS FOR (tu:TextUnit) REQUIRE tu.id IS UNIQUE")
            
            # Prepare batch data (iterrows is only for data preparation, not writing)
            batch_data = []
            for _, row in text_units.iterrows():
                text_unit_id = str(row.get("id", ""))
                if not text_unit_id:
                    continue
                batch_data.append({
                    "id": text_unit_id,
                    "text": str(row.get("text", "")) if pd.notna(row.get("text")) else "",
                    "n_tokens": row.get("n_tokens", None),
                    "document_ids": row.get("document_ids", []) if isinstance(row.get("document_ids"), list) else [],
                    "entity_ids": row.get("entity_ids", []) if isinstance(row.get("entity_ids"), list) else [],
                    "relationship_ids": row.get("relationship_ids", []) if isinstance(row.get("relationship_ids"), list) else [],
                    "covariate_ids": row.get("covariate_ids", []) if isinstance(row.get("covariate_ids"), list) else []
                })
            
            # Batch write text units using UNWIND
            if batch_data:
                session.run(
                    "UNWIND $rows AS row "
                    "MERGE (tu:TextUnit {id: row.id}) "
                    "SET tu.text = row.text, tu.n_tokens = row.n_tokens, tu.document_ids = row.document_ids, "
                    "tu.entity_ids = row.entity_ids, tu.relationship_ids = row.relationship_ids, "
                    "tu.covariate_ids = row.covariate_ids",
                    rows=batch_data
                )
            
            logger.info(f"Wrote {len(batch_data)} text units to Neo4j")
            return True
    except Exception as e:
        logger.warning(f"Error writing text units to Neo4j: {e}")
        return False
    finally:
        if driver is not None:
            driver.close()


# ============================================================================
def load_entities_from_neo4j() -> pd.DataFrame:
    """Load entities from Neo4j."""
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
    """Load communities from Neo4j."""
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
    """Load community reports from Neo4j."""
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
    """Load relationships from Neo4j."""
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
    """Load text units from Neo4j."""
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
    """Load documents from Neo4j."""
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
def run_cypher(query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Run an arbitrary Cypher query against Neo4j."""
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

