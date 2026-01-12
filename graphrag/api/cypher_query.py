# Copyright (c) 2024 Microsoft Corporation.
# Licensed under the MIT License

"""Cypher Query API for GraphRAG - Execute arbitrary Cypher queries against Neo4j."""

import asyncio
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


async def query_with_natural_language_async(
    question: str,
    config: Any,
    model_id: str | None = None,
    execute: bool = True,
) -> tuple[str, list[dict[str, Any]]]:
    """
    Generate and optionally execute a Cypher query from natural language.
    
    Similar to LlamaIndex's TextToCypherRetriever - converts natural language
    to Cypher and optionally executes it.
    
    Parameters
    ----------
    question : str
        Natural language question
    config : GraphRagConfig
        GraphRAG configuration
    model_id : str, optional
        Model ID for text-to-cypher generation
    execute : bool
        Whether to execute the generated query (default: True)
        
    Returns
    -------
    tuple[str, list[dict]]
        Generated Cypher query and results (empty list if execute=False)
    """
    # Generate Cypher query
    cypher_query = await generate_cypher_async(question, config, model_id)
    
    # Execute if requested
    results = []
    if execute and NEO4J_AVAILABLE:
        results = run_cypher(cypher_query)
    
    return cypher_query, results


def query_with_natural_language(
    question: str,
    config: Any,
    model_id: str | None = None,
    execute: bool = True,
) -> tuple[str, list[dict[str, Any]]]:
    """
    Generate and optionally execute a Cypher query from natural language (synchronous).
    
    Parameters
    ----------
    question : str
        Natural language question
    config : GraphRagConfig
        GraphRAG configuration
    model_id : str, optional
        Model ID for text-to-cypher generation
    execute : bool
        Whether to execute the generated query (default: True)
        
    Returns
    -------
    tuple[str, list[dict]]
        Generated Cypher query and results (empty list if execute=False)
    """
    return asyncio.run(query_with_natural_language_async(question, config, model_id, execute))


async def generate_cypher_async(
    question: str,
    config: Any,
    model_id: str | None = None,
    schema: dict[str, Any] | None = None,
) -> str:
    """
    Generate Cypher query from natural language using LLM.
    
    This is similar to LlamaIndex's TextToCypherRetriever - it uses the graph schema
    and an LLM to convert natural language questions into Cypher queries.
    
    Parameters
    ----------
    question : str
        Natural language question to convert to Cypher
    config : GraphRagConfig
        GraphRAG configuration object
    model_id : str, optional
        Model ID to use (defaults to default_chat_model)
    schema : dict, optional
        Neo4j schema information (will be fetched if not provided)
        
    Returns
    -------
    str
        Generated Cypher query string
    """
    from graphrag.language_model.manager import ModelManager
    
    # Get schema if not provided
    if schema is None:
        schema = get_cypher_schema()
    
    # Get model configuration
    model_id = model_id or "default_chat_model"
    try:
        model_settings = config.get_language_model_config(model_id)
    except Exception as e:
        logger.warning(f"Could not get model config for {model_id}, using default: {e}")
        model_settings = config.get_language_model_config("default_chat_model")
    
    # Create or get chat model
    chat_model = ModelManager().get_or_create_chat_model(
        name="cypher_generation",
        model_type=model_settings.type,
        config=model_settings,
    )
    
    # Build text-to-cypher prompt
    prompt = _build_text_to_cypher_prompt(question, schema)
    
    # Generate Cypher query using LLM
    try:
        response = await chat_model.achat(prompt)
        cypher_query = response.output.content.strip()
        
        # Clean up the response - remove markdown code blocks if present
        if cypher_query.startswith("```"):
            lines = cypher_query.split("\n")
            # Remove first line (```cypher or ```)
            lines = lines[1:]
            # Remove last line if it's ```
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cypher_query = "\n".join(lines).strip()
        
        logger.debug(f"Generated Cypher query: {cypher_query}")
        return cypher_query
    except Exception as e:
        logger.error(f"Error generating Cypher query: {e}")
        # Return a safe fallback query
        return f"// Error generating query: {e}\nMATCH (e:Entity) RETURN e LIMIT 10"


def generate_cypher(
    question: str,
    config: Any | None = None,
    model_id: str | None = None,
    schema: dict[str, Any] | None = None,
) -> str:
    """
    Generate Cypher query from natural language using LLM (synchronous wrapper).
    
    Parameters
    ----------
    question : str
        Natural language question to convert to Cypher
    config : GraphRagConfig, optional
        GraphRAG configuration object
    model_id : str, optional
        Model ID to use (defaults to default_chat_model)
    schema : dict, optional
        Neo4j schema information (will be fetched if not provided)
        
    Returns
    -------
    str
        Generated Cypher query string
    """
    if config is None:
        logger.warning("No config provided. Returning template query.")
        return f"// Generated query for: {question}\nMATCH (e:Entity) RETURN e LIMIT 10"
    
    return asyncio.run(generate_cypher_async(question, config, model_id, schema))


def _build_text_to_cypher_prompt(question: str, schema: dict[str, Any]) -> str:
    """Build the text-to-cypher prompt with schema information."""
    node_labels = schema.get("node_labels", [])
    relationship_types = schema.get("relationship_types", [])
    properties = schema.get("properties", {})
    
    # Build schema description
    schema_desc = "## Node Labels:\n"
    for label in node_labels:
        props = properties.get(label, [])
        schema_desc += f"- {label}: {', '.join(props) if props else 'no properties'}\n"
    
    schema_desc += "\n## Relationship Types:\n"
    for rel_type in relationship_types:
        schema_desc += f"- {rel_type}\n"
    
    # Build example queries
    examples = """
## Example Queries:

1. "Find all entities" → `MATCH (e:Entity) RETURN e LIMIT 10`
2. "Find documents mentioning Microsoft" → `MATCH (d:Document)-[:MENTIONS]->(e:Entity {name: 'Microsoft'}) RETURN d`
3. "Find entities related to Microsoft" → `MATCH (e1:Entity {name: 'Microsoft'})-[:RELATES_TO]->(e2:Entity) RETURN e2`
4. "Find all communities" → `MATCH (c:Community) RETURN c LIMIT 10`
"""
    
    prompt = f"""You are a Cypher query expert. Generate a Cypher query for Neo4j based on the user's question.

## Graph Schema:
{schema_desc}

{examples}

## Instructions:
- Generate ONLY the Cypher query, no explanations
- Use proper Cypher syntax
- Return only relevant properties (id, name, text, etc.)
- Use LIMIT when appropriate to avoid large result sets
- Match the node labels and relationship types exactly as shown in the schema

## User Question:
{question}

## Cypher Query:
"""
    return prompt


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
