# Copyright (c) 2024 Microsoft Corporation.
# Licensed under the MIT License

"""Diagnostic script to check Neo4j connection and configuration."""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv  # type: ignore[import-untyped]

# Load .env
repo_root = Path(__file__).parent.resolve()
env_path = repo_root / ".env"
if env_path.exists():
    load_dotenv(env_path, override=True)
    # Manually parse to ensure all keys loaded
    with env_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                key, value = key.strip(), value.strip().strip('"').strip("'")
                if value:
                    os.environ[key] = value

print("=" * 60)
print("Neo4j Connection Diagnostic")
print("=" * 60)

# Check environment variables
use_neo4j = os.getenv("GRAPHRAG_USE_NEO4J", "false").lower()
uri = os.getenv("NEO4J_URI")
user = os.getenv("NEO4J_USER")
password = os.getenv("NEO4J_PASSWORD")

print(f"\n[Configuration]")
print(f"  GRAPHRAG_USE_NEO4J: {use_neo4j}")
print(f"  NEO4J_URI: {uri or 'NOT SET'}")
print(f"  NEO4J_USER: {user or 'NOT SET'}")
print(f"  NEO4J_PASSWORD: {'*' * len(password) if password else 'NOT SET'}")

# Check if enabled
if use_neo4j != "true":
    print(f"\n[ERROR] Neo4j is not enabled!")
    print(f"  Set GRAPHRAG_USE_NEO4J=true in your .env file")
    sys.exit(1)

# Check if all required vars are set
if not all([uri, user, password]):
    print(f"\n[ERROR] Missing Neo4j connection details!")
    print(f"  Required in .env file:")
    print(f"    NEO4J_URI=bolt://localhost:7687")
    print(f"    NEO4J_USER=neo4j")
    print(f"    NEO4J_PASSWORD=your_password")
    sys.exit(1)

# Try to import Neo4j driver
try:
    from neo4j import GraphDatabase
    print(f"\n[OK] Neo4j Python driver installed")
except ImportError:
    print(f"\n[ERROR] Neo4j Python driver not installed!")
    print(f"  Install with: pip install neo4j")
    sys.exit(1)

# Try to connect
print(f"\n[Testing Connection]")
print(f"  Connecting to {uri}...")
try:
    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    print(f"  [OK] Successfully connected to Neo4j!")
    
    # Test a simple query
    with driver.session() as session:
        result = session.run("RETURN 1 as test")
        record = result.single()
        if record and record["test"] == 1:
            print(f"  [OK] Query test successful")
        
        # Check if database has data
        node_count = session.run("MATCH (n) RETURN count(n) as count").single()["count"]
        print(f"  [OK] Database has {node_count} nodes")
        
        # Check for GraphRAG nodes
        entity_count = session.run("MATCH (e:Entity) RETURN count(e) as count").single()["count"]
        doc_count = session.run("MATCH (d:Document) RETURN count(d) as count").single()["count"]
        print(f"  [OK] Entities: {entity_count}, Documents: {doc_count}")
    
    driver.close()
    print(f"\n[SUCCESS] Neo4j is running and accessible!")
    
except Exception as e:
    print(f"\n[ERROR] Failed to connect to Neo4j!")
    print(f"  Error: {e}")
    print(f"\n[Troubleshooting]")
    print(f"  1. Is Neo4j running? Check with: docker ps (if using Docker)")
    print(f"  2. Is the URI correct? Try: bolt://localhost:7687 or neo4j://localhost:7687")
    print(f"  3. Are credentials correct? Default user is 'neo4j'")
    print(f"  4. Is Neo4j listening on the correct port?")
    print(f"  5. If using Docker: docker run -e NEO4J_AUTH=neo4j/password -p 7687:7687 neo4j")
    sys.exit(1)
