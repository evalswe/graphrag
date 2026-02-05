# Copyright (c) 2024 Microsoft Corporation.
# Licensed under the MIT License

"""Util functions to retrieve text units from a collection."""

from typing import Any, cast

import pandas as pd

from graphrag.data_model.entity import Entity
from graphrag.data_model.text_unit import TextUnit


def _get_documents_by_entity_neo4j(entity_name: str) -> list[dict[str, Any]]:
    """Get documents mentioning an entity from Neo4j."""
    from graphrag.graphrag.graph.neo4j_client import get_documents_by_entity_neo4j as neo4j_func
    return neo4j_func(entity_name)


def get_candidate_text_units(
    selected_entities: list[Entity],
    text_units: list[TextUnit],
) -> pd.DataFrame:
    """Get all text units that are associated to selected entities.
    
    Note: Currently returns a DataFrame. Future optimization: consider operating
    directly on Neo4j without converting to dataframes to reduce memory usage.
    """
    neo4j_text_units = []
    for entity in selected_entities:
        if entity.title:
            neo4j_docs = _get_documents_by_entity_neo4j(entity.title)
            for doc in neo4j_docs:
                doc_text = doc.get("text", "") or doc.get("source", "") or doc.get("title", "")
                text_unit = TextUnit(
                    id=doc.get("id", ""),
                    short_id=doc.get("id", ""),
                    text=doc_text,
                    document_ids=[doc.get("id", "")]
                )
                neo4j_text_units.append(text_unit)
    
    if neo4j_text_units:
        return to_text_unit_dataframe(neo4j_text_units)
    
    return pd.DataFrame()


def to_text_unit_dataframe(text_units: list[TextUnit]) -> pd.DataFrame:
    """Convert a list of text units to a pandas dataframe."""
    if len(text_units) == 0:
        return pd.DataFrame()

    # add header
    header = ["id", "text"]
    attribute_cols = (
        list(text_units[0].attributes.keys()) if text_units[0].attributes else []
    )
    attribute_cols = [col for col in attribute_cols if col not in header]
    header.extend(attribute_cols)

    records = []
    for unit in text_units:
        new_record = [
            unit.short_id,
            unit.text,
            *[
                str(unit.attributes.get(field, ""))
                if unit.attributes and unit.attributes.get(field)
                else ""
                for field in attribute_cols
            ],
        ]
        records.append(new_record)
    return pd.DataFrame(records, columns=cast("Any", header))
