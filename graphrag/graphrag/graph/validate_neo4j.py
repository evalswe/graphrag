# Copyright (c) 2024 Microsoft Corporation.
# Licensed under the MIT License

"""
EXPERIMENTAL: Validation script for Neo4j graph data.

This script validates that GraphRAG indexing output has been correctly
persisted to Neo4j. It checks:
- Documents exist in Neo4j
- Entities exist in Neo4j
- MENTIONS relationships exist
- Retrieval via Cypher returns expected documents

This is a script-based validation tool (not a service).
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def validate_neo4j_data() -> dict[str, Any]:
    """
    EXPERIMENTAL: Validate Neo4j graph data integrity.
    
    Returns
    -------
    dict
        Validation results with counts and status
    """
    try:
        from graphrag.graph.neo4j_client import run_cypher, _is_neo4j_enabled
    except ImportError:
        return {
            "status": "error",
            "message": "Neo4j client not available. Install neo4j package."
        }
    
    if not _is_neo4j_enabled():
        return {
            "status": "disabled",
            "message": "Neo4j is not enabled. Set GRAPHRAG_USE_NEO4J=true"
        }
    
    results = {
        "status": "success",
        "documents": 0,
        "entities": 0,
        "mentions": 0,
        "sample_documents": [],
        "sample_entities": [],
        "errors": []
    }
    
    try:
        # Count documents
        doc_count = run_cypher("MATCH (d:Document) RETURN count(d) as count")
        if doc_count:
            results["documents"] = doc_count[0].get("count", 0)
        
        # Count entities
        entity_count = run_cypher("MATCH (e:Entity) RETURN count(e) as count")
        if entity_count:
            results["entities"] = entity_count[0].get("count", 0)
        
        # Count MENTIONS relationships
        mentions_count = run_cypher("MATCH ()-[r:MENTIONS]->() RETURN count(r) as count")
        if mentions_count:
            results["mentions"] = mentions_count[0].get("count", 0)
        
        # Get sample documents
        sample_docs = run_cypher(
            "MATCH (d:Document) RETURN d.id as id, d.source as source LIMIT 5"
        )
        results["sample_documents"] = sample_docs
        
        # Get sample entities
        sample_entities = run_cypher(
            "MATCH (e:Entity) RETURN e.id as id, e.name as name, e.type as type LIMIT 5"
        )
        results["sample_entities"] = sample_entities
        
        # Validate relationships exist
        if results["documents"] > 0 and results["entities"] > 0:
            # Check if any documents have MENTIONS relationships
            doc_with_mentions = run_cypher(
                "MATCH (d:Document)-[:MENTIONS]->(e:Entity) RETURN count(DISTINCT d) as count"
            )
            docs_with_mentions = doc_with_mentions[0].get("count", 0) if doc_with_mentions else 0
            
            if docs_with_mentions == 0 and results["mentions"] == 0:
                results["errors"].append(
                    "Warning: No MENTIONS relationships found between documents and entities"
                )
        
    except Exception as e:
        results["status"] = "error"
        results["errors"].append(f"Validation error: {str(e)}")
        logger.error(f"Neo4j validation error: {e}", exc_info=True)
    
    return results


def print_validation_report(results: dict[str, Any]) -> None:
    """Print a human-readable validation report."""
    print("=" * 60)
    print("Neo4j Graph Data Validation Report")
    print("=" * 60)
    print(f"Status: {results['status']}")
    print()
    
    if results["status"] == "disabled":
        print(results.get("message", "Neo4j is disabled"))
        return
    
    if results["status"] == "error":
        print("ERROR: Validation failed")
        for error in results.get("errors", []):
            print(f"  - {error}")
        return
    
    print("Data Counts:")
    print(f"  Documents: {results['documents']}")
    print(f"  Entities: {results['entities']}")
    print(f"  MENTIONS relationships: {results['mentions']}")
    print()
    
    if results["sample_documents"]:
        print("Sample Documents:")
        for doc in results["sample_documents"][:3]:
            print(f"  - {doc.get('source', 'N/A')} (id: {doc.get('id', 'N/A')})")
        print()
    
    if results["sample_entities"]:
        print("Sample Entities:")
        for entity in results["sample_entities"][:3]:
            print(f"  - {entity.get('name', 'N/A')} ({entity.get('type', 'N/A')})")
        print()
    
    if results.get("errors"):
        print("Warnings/Errors:")
        for error in results["errors"]:
            print(f"  - {error}")
        print()
    
    # Validation summary
    if results["documents"] > 0 and results["entities"] > 0 and results["mentions"] > 0:
        print("✓ Validation PASSED: All data types present in Neo4j")
    elif results["documents"] == 0 and results["entities"] == 0:
        print("✗ Validation FAILED: No data found in Neo4j")
        print("  Make sure indexing completed with GRAPHRAG_USE_NEO4J=true")
    else:
        print("⚠ Validation INCOMPLETE: Some data missing")
    
    print("=" * 60)


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    
    # Run validation
    results = validate_neo4j_data()
    print_validation_report(results)


