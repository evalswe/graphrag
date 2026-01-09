#!/usr/bin/env python3
"""
Quick validation script to verify Neo4j integration is working.
This script checks:
1. Neo4j connection
2. Core functions are importable
3. Data exists in Neo4j (if indexing has been run)
"""

import os
import sys
from pathlib import Path

# Fix Unicode encoding on Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Add graphrag to path
repo_root = Path(__file__).parent.resolve()
graphrag_path = repo_root / "graphrag"
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(graphrag_path))

def check_imports():
    """Check that Neo4j client functions can be imported."""
    print("=" * 60)
    print("TEST 1: Checking imports...")
    print("=" * 60)
    try:
        from graphrag.graphrag.graph.neo4j_client import (
            run_cypher,
            write_documents_to_neo4j,
            write_entities_to_neo4j,
            get_entity_by_name_neo4j,
            get_documents_by_entity_neo4j,
        )
        print("[OK] All Neo4j functions imported successfully")
        return True
    except ImportError as e:
        print(f"[FAIL] Import failed: {e}")
        return False

def check_neo4j_connection():
    """Check Neo4j connection."""
    print("\n" + "=" * 60)
    print("TEST 2: Checking Neo4j connection...")
    print("=" * 60)
    
    # Check environment variables
    use_neo4j = os.getenv("GRAPHRAG_USE_NEO4J", "false").lower()
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")
    
    print(f"GRAPHRAG_USE_NEO4J: {use_neo4j}")
    print(f"NEO4J_URI: {uri}")
    print(f"NEO4J_USER: {user}")
    print(f"NEO4J_PASSWORD: {'*' * len(password) if password else 'NOT SET'}")
    
    if use_neo4j != "true":
        print("[WARN] Neo4j is not enabled (GRAPHRAG_USE_NEO4J != true)")
        return False
    
    if not all([uri, user, password]):
        print("[FAIL] Neo4j connection details are missing")
        return False
    
    try:
        from graphrag.graphrag.graph.neo4j_client import run_cypher
        result = run_cypher("RETURN 1 as test")
        if result:
            print("[OK] Neo4j connection successful")
            return True
        else:
            print("[FAIL] Neo4j connection failed (no result)")
            return False
    except Exception as e:
        print(f"[FAIL] Neo4j connection failed: {e}")
        return False

def check_data_in_neo4j():
    """Check if data exists in Neo4j."""
    print("\n" + "=" * 60)
    print("TEST 3: Checking data in Neo4j...")
    print("=" * 60)
    
    try:
        from graphrag.graphrag.graph.neo4j_client import run_cypher
        
        # Count documents
        doc_result = run_cypher("MATCH (d:Document) RETURN count(d) as count")
        doc_count = doc_result[0]["count"] if doc_result else 0
        
        # Count entities
        entity_result = run_cypher("MATCH (e:Entity) RETURN count(e) as count")
        entity_count = entity_result[0]["count"] if entity_result else 0
        
        # Count relationships
        rel_result = run_cypher("MATCH ()-[r:MENTIONS]->() RETURN count(r) as count")
        rel_count = rel_result[0]["count"] if rel_result else 0
        
        print(f"Documents: {doc_count}")
        print(f"Entities: {entity_count}")
        print(f"Relationships: {rel_count}")
        
        if doc_count > 0 and entity_count > 0:
            print("[OK] Data exists in Neo4j")
            return True
        else:
            print("[WARN] No data found in Neo4j (run indexing with GRAPHRAG_USE_NEO4J=true)")
            return False
    except Exception as e:
        print(f"[FAIL] Error checking data: {e}")
        return False

def check_integration_points():
    """Check that integration points exist in codebase."""
    print("\n" + "=" * 60)
    print("TEST 4: Checking integration points...")
    print("=" * 60)
    
    integration_files = [
        "graphrag/graphrag/graph/neo4j_client.py",
        "graphrag/index/workflows/create_final_documents.py",
        "graphrag/graphrag/query/input/retrieval/text_units.py",
        "graphrag/graphrag/query/context_builder/entity_extraction.py",
    ]
    
    all_exist = True
    for file_path in integration_files:
        full_path = repo_root / file_path
        if full_path.exists():
            print(f"[OK] {file_path}")
        else:
            print(f"[FAIL] {file_path} - NOT FOUND")
            all_exist = False
    
    return all_exist

def main():
    """Run all validation tests."""
    print("\n" + "=" * 60)
    print("Neo4j Integration Validation")
    print("=" * 60)
    
    results = []
    
    # Test 1: Imports
    results.append(("Imports", check_imports()))
    
    # Test 2: Connection
    results.append(("Neo4j Connection", check_neo4j_connection()))
    
    # Test 3: Data
    results.append(("Data in Neo4j", check_data_in_neo4j()))
    
    # Test 4: Integration points
    results.append(("Integration Points", check_integration_points()))
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{test_name}: {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n[SUCCESS] All tests passed! Neo4j integration is working.")
        return 0
    else:
        print("\n[WARN] Some tests failed. Check the output above for details.")
        return 1

if __name__ == "__main__":
    sys.exit(main())

