# Copyright (c) 2024 Microsoft Corporation.
# Licensed under the MIT License

"""Orchestration Context Builders."""

from enum import Enum

from graphrag.data_model.entity import Entity
from graphrag.data_model.relationship import Relationship
from graphrag.language_model.protocol.base import EmbeddingModel
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
            from graphrag.graphrag.graph.neo4j_client import (
                get_entity_by_id_neo4j,
                get_entity_by_name_neo4j,
            )
            
            if embedding_vectorstore_key == EntityVectorStoreKey.ID and isinstance(
                result.document.id, str
            ):
                neo4j_entity = get_entity_by_id_neo4j(result.document.id)
            else:
                # For TITLE key, use name lookup
                neo4j_entity = get_entity_by_name_neo4j(str(result.document.id))
            
            if neo4j_entity:
                matched = Entity(
                    id=neo4j_entity.get("id", ""),
                    title=neo4j_entity.get("name", ""),
                    type=neo4j_entity.get("type")
                )
                matched_entities.append(matched)
    else:
        # Load entities from Neo4j sorted by rank
        from graphrag.graphrag.graph.neo4j_client import load_entities_from_neo4j
        
        entities_df = load_entities_from_neo4j()
        if not entities_df.empty:
            # Sort by rank (if available) and take top k
            if "rank" in entities_df.columns:
                entities_df = entities_df.sort_values("rank", ascending=False, na_position="last")
            matched_entities = [
                Entity(
                    id=str(row.get("id", "")),
                    title=str(row.get("title", "")),
                    type=row.get("type"),
                    rank=row.get("rank")
                )
                for _, row in entities_df.head(k).iterrows()
            ]

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
        from graphrag.graphrag.graph.neo4j_client import get_entity_by_name_neo4j
        
        neo4j_entity = get_entity_by_name_neo4j(entity_name)
        if neo4j_entity:
            entity = Entity(
                id=neo4j_entity.get("id", ""),
                title=neo4j_entity.get("name", entity_name),
                type=neo4j_entity.get("type")
            )
            included_entities.append(entity)
    return included_entities + matched_entities


def find_nearest_neighbors_by_entity_rank(
    entity_name: str,
    all_entities: list[Entity] | None = None,
    all_relationships: list[Relationship] | None = None,
    exclude_entity_names: list[str] | None = None,
    k: int | None = 10,
) -> list[Entity]:
    """Retrieve entities that have direct connections with the target entity, sorted by entity rank."""
    from graphrag.graphrag.graph.neo4j_client import get_connected_entities_neo4j
    
    # Query Neo4j for connected entities
    connected_entities_data = get_connected_entities_neo4j(
        entity_name=entity_name,
        exclude_entity_names=exclude_entity_names,
        k=k
    )
    
    # Convert to Entity objects
    connected_entities = [
        Entity(
            id=entity_data.get("id", ""),
            title=entity_data.get("name", ""),
            type=entity_data.get("type"),
            rank=entity_data.get("rank")
        )
        for entity_data in connected_entities_data
    ]
    
    return connected_entities
