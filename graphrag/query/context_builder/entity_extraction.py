# Copyright (c) 2024 Microsoft Corporation.
# Licensed under the MIT License

"""Orchestration Context Builders."""

from enum import Enum
from typing import Any

from graphrag.data_model.entity import Entity
from graphrag.data_model.relationship import Relationship
from graphrag.graphrag.graph.neo4j_client import (
    get_connected_entities_neo4j,
    get_entity_by_id_neo4j,
    get_entity_by_name_neo4j,
    load_entities_from_neo4j,
)
from graphrag.language_model.protocol.base import EmbeddingModel
from graphrag.query.input.retrieval.entities import (
    get_entity_by_id,
    get_entity_by_key,
    get_entity_by_name,
)
from graphrag.vector_stores.base import BaseVectorStore


class EntityVectorStoreKey(str, Enum):
    """Keys used as ids in the entity embedding vectorstores."""

    ID = "id"
    TITLE = "title"

    @staticmethod
    def from_string(value: str) -> "EntityVectorStoreKey":
        """Convert string to EntityVectorStoreKey."""
        if value == "id":
            return EntityVectorStoreKey.ID
        if value == "title":
            return EntityVectorStoreKey.TITLE

        msg = f"Invalid EntityVectorStoreKey: {value}"
        raise ValueError(msg)


def _neo4j_dict_to_entity(entity_dict: dict[str, Any]) -> Entity:
    """Convert Neo4j entity dict to Entity object."""
    # Map Neo4j "name" to Entity "title"
    entity_data = {
        "id": entity_dict.get("id"),
        "title": entity_dict.get("name", entity_dict.get("title", "")),
        "type": entity_dict.get("type"),
        "rank": entity_dict.get("rank", 1),
    }
    return Entity.from_dict(entity_data, title_key="title")


def map_query_to_entities(
    query: str,
    text_embedding_vectorstore: BaseVectorStore,
    text_embedder: EmbeddingModel,
    all_entities_dict: dict[str, Entity],
    embedding_vectorstore_key: str = EntityVectorStoreKey.ID,
    include_entity_names: list[str] | None = None,
    exclude_entity_names: list[str] | None = None,
    k: int = 10,
    oversample_scaler: int = 2,
) -> list[Entity]:
    """Extract entities that match a given query using semantic similarity of text embeddings of query and entity descriptions."""
    if include_entity_names is None:
        include_entity_names = []
    if exclude_entity_names is None:
        exclude_entity_names = []
    all_entities = list(all_entities_dict.values())
    matched_entities = []
    if query != "":
        # get entities with highest semantic similarity to query
        # oversample to account for excluded entities
        search_results = text_embedding_vectorstore.similarity_search_by_text(
            text=query,
            text_embedder=lambda t: text_embedder.embed(t),
            k=k * oversample_scaler,
        )
        for result in search_results:
            matched = None
            if embedding_vectorstore_key == EntityVectorStoreKey.ID and isinstance(
                result.document.id, str
            ):
                # Try Neo4j first
                entity_dict = get_entity_by_id_neo4j(result.document.id)
                if entity_dict:
                    matched = _neo4j_dict_to_entity(entity_dict)
                else:
                    # Fallback to in-memory dict if available
                    matched = get_entity_by_id(all_entities_dict, result.document.id)
            else:
                # For title-based lookup, try Neo4j by name
                if embedding_vectorstore_key == EntityVectorStoreKey.TITLE:
                    entity_dict = get_entity_by_name_neo4j(result.document.id)
                    if entity_dict:
                        matched = _neo4j_dict_to_entity(entity_dict)
                # Fallback to in-memory lookup if available
                if not matched:
                    matched = get_entity_by_key(
                        entities=all_entities,
                        key=embedding_vectorstore_key,
                        value=result.document.id,
                    )
            if matched:
                matched_entities.append(matched)
    else:
        # Load entities from Neo4j sorted by rank
        entities_df = load_entities_from_neo4j()
        if not entities_df.empty:
            # Convert DataFrame to Entity objects and sort by rank
            neo4j_entities = []
            for _, row in entities_df.iterrows():
                entity_data = {
                    "id": row.get("id"),
                    "title": row.get("title", ""),
                    "type": row.get("type"),
                }
                entity = Entity.from_dict(entity_data, title_key="title")
                # Get rank from Neo4j if available (would need to enhance query)
                entity.rank = 1  # Default rank, could be enhanced
                neo4j_entities.append(entity)
            neo4j_entities.sort(key=lambda x: x.rank if x.rank else 0, reverse=True)
            matched_entities = neo4j_entities[:k]
        else:
            # Fallback to in-memory entities if Neo4j unavailable
            all_entities.sort(key=lambda x: x.rank if x.rank else 0, reverse=True)
            matched_entities = all_entities[:k]

    # filter out excluded entities
    if exclude_entity_names:
        matched_entities = [
            entity
            for entity in matched_entities
            if entity.title not in exclude_entity_names
        ]

    # add entities in the include_entity list
    included_entities = []
    for entity_name in include_entity_names:
        # Try Neo4j first
        entity_dict = get_entity_by_name_neo4j(entity_name)
        if entity_dict:
            included_entities.append(_neo4j_dict_to_entity(entity_dict))
        else:
            # Fallback to in-memory lookup if available
            included_entities.extend(get_entity_by_name(all_entities, entity_name))
    return included_entities + matched_entities


def find_nearest_neighbors_by_entity_rank(
    entity_name: str,
    all_entities: list[Entity] | None = None,
    all_relationships: list[Relationship] | None = None,
    exclude_entity_names: list[str] | None = None,
    k: int | None = 10,
) -> list[Entity]:
    """Retrieve entities that have direct connections with the target entity, sorted by entity rank."""
    if exclude_entity_names is None:
        exclude_entity_names = []
    
    # Query Neo4j directly for connected entities
    # This avoids loading all relationships into memory
    connected_entities_dicts = get_connected_entities_neo4j(
        entity_name=entity_name,
        exclude_entity_names=exclude_entity_names,
        k=k
    )
    
    # Convert Neo4j results to Entity objects
    return [_neo4j_dict_to_entity(entity_dict) for entity_dict in connected_entities_dicts]
