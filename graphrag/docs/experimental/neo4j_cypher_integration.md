# Neo4j Cypher Integration (Experimental)

## Overview

This is an **experimental integration** to replace dataframe-based READ operations during query time with Neo4j-backed reads using Cypher queries directly.

**Status**: Experimental - Not for production use

## Scope

### What Was Changed

This integration makes **minimal, targeted changes** to support Neo4j with Cypher:

1. **Indexing → Neo4j Write Path** (`graphrag/index/workflows/create_final_documents.py`)
   - After indexing completes, automatically writes documents, entities, and MENTIONS relationships to Neo4j
   - Feature-flagged via `GRAPHRAG_USE_NEO4J` environment variable

2. **Query → Neo4j Read Path**
   - **Entity lookup by name** (`graphrag/query/context_builder/entity_extraction.py`)
     - When entities are looked up by name during query execution, Neo4j is attempted first
     - Falls back to existing dataframe logic if Neo4j is unavailable
   - **Entity→Document relationship lookup** (`graphrag/query/input/retrieval/text_units.py`)
     - When finding documents/text units that mention an entity, Neo4j is attempted first
     - Falls back to existing dataframe logic if Neo4j is unavailable

3. **Cypher Query Utility** (`graphrag/graph/neo4j_client.py`)
   - `run_cypher()` function for arbitrary Cypher queries (notebook/exploration use only)

### What Was NOT Changed

- ✅ Indexing logic remains unchanged (still writes to parquet files)
- ✅ Embedding logic remains unchanged
- ✅ Defaults and prompts are unchanged
- ✅ Settings.yaml behavior is unchanged
- ✅ All existing GraphRAG functionality is preserved

## Architecture

### Neo4j Data Model

The integration uses a minimal schema aligned with LlamaIndex LPG concepts:

```cypher
(:Document {id, text, source})
(:Entity {id, name, type})
(:Document)-[:MENTIONS]->(:Entity)
```

**No additional nodes, relationships, or properties are used.**

### Feature Flag

Neo4j usage is controlled by environment variable:

```bash
GRAPHRAG_USE_NEO4J=true
```

When disabled (default), all operations use existing dataframe logic.

### Neo4j Connection

Neo4j connection details are read from environment variables:

- `NEO4J_URI` - Neo4j connection URI (e.g., `bolt://localhost:7687` or `neo4j+s://xxxx.databases.neo4j.io`)
- `NEO4J_USER` - Neo4j username
- `NEO4J_PASSWORD` - Neo4j password

If connection fails or Neo4j is unavailable, the system gracefully falls back to dataframe reads.

## Usage

### Indexing with Neo4j

When `GRAPHRAG_USE_NEO4J=true`, indexing automatically writes to Neo4j:

```python
import os
os.environ["GRAPHRAG_USE_NEO4J"] = "true"
os.environ["NEO4J_URI"] = "bolt://localhost:7687"
os.environ["NEO4J_USER"] = "neo4j"
os.environ["NEO4J_PASSWORD"] = "your_password"

from graphrag.api.index import build_index
from graphrag.config.load_config import load_config
import asyncio

config = load_config("path/to/config.yaml")
results = asyncio.run(build_index(config, verbose=True))
# Data is automatically written to Neo4j during indexing
```

### Querying with Cypher

Use the `run_cypher()` utility for exploration and notebooks:

```python
from graphrag.graph.neo4j_client import run_cypher

# Get all entities
entities = run_cypher("MATCH (e:Entity) RETURN e.id as id, e.name as name, e.type as type LIMIT 10")

# Get documents mentioning an entity
docs = run_cypher(
    "MATCH (d:Document)-[:MENTIONS]->(e:Entity {name: $name}) RETURN d.id as id, d.text as text, d.source as source",
    params={"name": "Microsoft"}
)

# Count documents per entity
counts = run_cypher(
    "MATCH (d:Document)-[:MENTIONS]->(e:Entity) "
    "RETURN e.name as entity_name, e.type as entity_type, count(d) as doc_count "
    "ORDER BY doc_count DESC LIMIT 10"
)
```

### Query-Time Retrieval

GraphRAG query operations automatically use Neo4j for retrieval when enabled:

```python
from graphrag.api.query import query_index

# Standard GraphRAG query (uses Neo4j internally if enabled)
response = asyncio.run(query_index(
    config=config,
    query="What is Microsoft?",
    local=True,
    verbose=True
))
```

## Setup

### Prerequisites

1. **Neo4j Database**: A running Neo4j instance
   - Local: `docker run -e NEO4J_AUTH=neo4j/password -p 7687:7687 -p 7474:7474 neo4j`
   - Cloud: [Neo4j Aura](https://console.neo4j.io) or other cloud providers

2. **Python Dependencies**:
   ```bash
   pip install neo4j
   ```

### Environment Configuration

Add to your `.env` file or environment:

```bash
# Enable Neo4j (disabled by default)
GRAPHRAG_USE_NEO4J=true

# Neo4j connection details
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
```

## Data Population

**Automatic**: When `GRAPHRAG_USE_NEO4J=true`, indexing automatically populates Neo4j with:
- Documents (from `create_final_documents` workflow)
- Entities (from `finalize_graph` workflow)
- MENTIONS relationships (derived from entity text_unit_ids → document text_unit_ids)

No manual data population is required.

## Code Locations

- **Neo4j Client**: `graphrag/graph/neo4j_client.py`
  - Write functions: `write_documents_to_neo4j()`, `write_entities_to_neo4j()`, `write_mentions_to_neo4j()`
  - Read functions: `get_entity_by_name_neo4j()`, `get_documents_by_entity_neo4j()`
  - Utility: `run_cypher()`
- **Indexing Integration**: `graphrag/index/workflows/create_final_documents.py`
- **Query Integration**: 
  - `graphrag/query/context_builder/entity_extraction.py` (entity lookup)
  - `graphrag/query/input/retrieval/text_units.py` (document lookup)
- **Validation**: `graphrag/graph/validate_neo4j.py`
- **Demo Notebook**: `examples_notebooks/community_contrib/neo4j/neo4j_cypher_demo.ipynb`

## Validation

Validate Neo4j data integrity:

```python
from graphrag.graph.validate_neo4j import validate_neo4j_data, print_validation_report

results = validate_neo4j_data()
print_validation_report(results)
```

Or run from command line:

```bash
python -m graphrag.graph.validate_neo4j
```

## Limitations and Considerations

1. **Experimental**: This is experimental code, not production-ready
2. **Feature-flagged**: All Neo4j functionality is optional and disabled by default
3. **Fallback logic**: If Neo4j fails, dataframe logic is used automatically
4. **Minimal schema**: Uses only Document, Entity, and MENTIONS (no additional graph structure)
5. **Cypher-only**: Uses Cypher queries directly, no GraphQL or server components

## Future Work

Potential next steps could include:
- Additional query operations
- Performance optimization
- Production hardening
- Extended schema support

However, this integration intentionally remains minimal to assess feasibility without extensive changes to the codebase.

