# Neo4j-Centric Architecture Migration Plan

## Current State Assessment ✅

### What's Already Implemented

1. **Neo4j Client (`graphrag/graph/neo4j_client.py`)** ✅
   - ✅ Cypher-based (no GraphQL)
   - ✅ Write functions: `write_documents_to_neo4j()`, `write_entities_to_neo4j()`, `write_relationships_to_neo4j()`, `write_text_units_to_neo4j()`, `write_communities_to_neo4j()`
   - ✅ Read functions: `load_entities_from_neo4j()`, `load_relationships_from_neo4j()`, etc.
   - ✅ Utility: `run_cypher()` for arbitrary Cypher queries
   - ✅ Feature-flagged via `GRAPHRAG_USE_NEO4J` environment variable

2. **Indexing Integration** ✅
   - ✅ `finalize_graph.py` writes relationships to Neo4j
   - ✅ `create_final_documents.py` writes documents, entities, mentions
   - ✅ Automatic population during indexing when enabled

3. **Query Integration (Partial)** ⚠️
   - ✅ `entity_extraction.py` - entity lookup by name (Neo4j first, fallback to dataframe)
   - ✅ `text_units.py` - document lookup by entity (Neo4j first, fallback to dataframe)
   - ⚠️ Most query operations still use dataframes as primary source

## Target Architecture (Ideal World)

```
Files → GraphRAG Indexing → Neo4j → Query (Cypher/GQL)
```

### Key Requirements:
1. ✅ **Data comes in as files** - Already works
2. ✅ **Index runs GraphRAG logic** - Already works
3. ⚠️ **Saves to Neo4j** - Partially implemented (writes happen, but not all data)
4. ❌ **Query uses Neo4j instead of dataframes** - Needs work
5. ❌ **Arbitrary CypherQL/GQL generation** - Needs implementation

## Migration Steps

### Phase 1: Complete Neo4j Write Coverage ✅ (Mostly Done)

**Status**: ~80% Complete

**Remaining Work**:
- [ ] Ensure ALL workflows write to Neo4j (not just finalize_graph)
- [ ] Write text_units during `create_final_text_units` workflow
- [ ] Write all relationships (not just in finalize_graph)
- [ ] Add batch writing for performance

**Files to Update**:
- `graphrag/index/workflows/create_final_text_units.py` - Add Neo4j write
- `graphrag/index/workflows/create_final_documents.py` - Verify all writes
- `graphrag/index/workflows/finalize_graph.py` - Already has some writes

### Phase 2: Replace DataFrame Reads with Neo4j Reads ❌ (Needs Work)

**Status**: ~20% Complete

**Current Issue**: Query operations still load from parquet files first, Neo4j is fallback.

**Required Changes**:

1. **Update Query API Functions** (`graphrag/api/query.py`):
   - `local_search()` - Load entities, relationships, text_units from Neo4j
   - `global_search()` - Load entities, communities, community_reports from Neo4j
   - `drift_search()` - Load all data from Neo4j
   - `basic_search()` - Load text_units from Neo4j

2. **Update CLI Query** (`graphrag/cli/query.py`):
   - `_load_from_neo4j_or_storage()` - Make Neo4j primary, storage fallback
   - All query commands should check `GRAPHRAG_USE_NEO4J` first

3. **Update Context Builders**:
   - `graphrag/query/context_builder/entity_extraction.py` - Already has Neo4j
   - `graphrag/query/input/retrieval/text_units.py` - Already has Neo4j
   - Add Neo4j reads to other retrieval functions

**Files to Update**:
- `graphrag/api/query.py` - All search functions
- `graphrag/cli/query.py` - Load logic
- `graphrag/query/input/loaders/dfs.py` - Add Neo4j loaders

### Phase 3: Arbitrary Cypher/GQL Query Generation ❌ (Not Started)

**Status**: 0% Complete

**Reference**: [LlamaIndex LPG Guide](https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide/#retrieval-and-querying)

**Required Features**:
1. **Cypher Query Builder**:
   - Generate Cypher queries from natural language
   - Support complex graph traversals
   - Support aggregations and filtering

2. **GQL Support** (if needed):
   - GraphQL query generation
   - Schema introspection

3. **Query Interface**:
   - Notebook-friendly API
   - LLM-powered query generation (optional)

**New Files to Create**:
- `graphrag/query/cypher_builder.py` - Cypher query construction
- `graphrag/query/cypher_generator.py` - LLM-powered Cypher generation
- `graphrag/api/cypher_query.py` - Public API for Cypher queries

**Example API**:
```python
from graphrag.api.cypher_query import query_cypher, generate_cypher

# Direct Cypher query
results = query_cypher(
    "MATCH (e:Entity)-[:RELATES_TO]->(e2:Entity) RETURN e.name, e2.name LIMIT 10"
)

# LLM-generated Cypher
cypher_query = generate_cypher(
    query="Find all entities related to Microsoft",
    config=config
)
results = query_cypher(cypher_query)
```

## Implementation Priority

### High Priority (Core Functionality)
1. ✅ Complete Neo4j write coverage (Phase 1)
2. ❌ Replace dataframe reads in query operations (Phase 2)
3. ❌ Add Cypher query builder (Phase 3)

### Medium Priority (Enhancements)
- Performance optimization (batch writes, connection pooling)
- Query result caching
- Error handling and retry logic

### Low Priority (Nice to Have)
- GraphQL support
- Query visualization
- Performance metrics

## Code Locations Reference

### Neo4j Integration
- **Client**: `graphrag/graph/neo4j_client.py`
- **Indexing**: `graphrag/index/workflows/*.py`
- **Query**: `graphrag/query/**/*.py`
- **CLI**: `graphrag/cli/query.py`

### Query Operations
- **API**: `graphrag/api/query.py`
- **Context Builders**: `graphrag/query/context_builder/*.py`
- **Retrieval**: `graphrag/query/input/retrieval/*.py`
- **Loaders**: `graphrag/query/input/loaders/*.py`

## Testing Strategy

1. **Unit Tests**: Test Neo4j read/write functions
2. **Integration Tests**: Test full indexing → query flow
3. **Notebook Tests**: Test Cypher query generation
4. **Fallback Tests**: Ensure dataframe fallback works when Neo4j unavailable

## Environment Variables

```bash
# Enable Neo4j (required)
GRAPHRAG_USE_NEO4J=true

# Neo4j connection
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
```

## Next Steps

1. **Immediate**: Complete Phase 1 (ensure all data writes to Neo4j)
2. **Short-term**: Implement Phase 2 (replace dataframe reads)
3. **Medium-term**: Implement Phase 3 (Cypher query generation)
4. **Long-term**: Performance optimization and production hardening
