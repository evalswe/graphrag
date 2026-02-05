import json
import logging
import os

import pandas as pd
from neo4j import GraphDatabase

from graphrag.config.embeddings import (
    community_full_content_embedding,
    entity_description_embedding,
    text_unit_text_embedding,
)
from graphrag.config.models.graph_rag_config import GraphRagConfig
from graphrag.index.typing.context import PipelineRunContext
from graphrag.index.typing.workflow import WorkflowFunctionOutput
from graphrag.utils.storage import (
    load_table_from_storage,
    storage_has_table,
)

logger = logging.getLogger(__name__)


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    if isinstance(value, float) and pd.isna(value):
        return []
    if pd.isna(value):
        return []
    return []


async def run_workflow(
    config: GraphRagConfig,
    context: PipelineRunContext,
) -> WorkflowFunctionOutput:
    """Export GraphRAG tables + embeddings to Neo4j."""
    logger.info("Workflow started: export_to_neo4j_full")

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")

    driver = GraphDatabase.driver(uri, auth=(user, password))

    documents = await load_table_from_storage("documents", context.output_storage)
    text_units = await load_table_from_storage("text_units", context.output_storage)
    entities = await load_table_from_storage("entities", context.output_storage)
    relationships = await load_table_from_storage("relationships", context.output_storage)
    communities = await load_table_from_storage("communities", context.output_storage)
    community_reports = await load_table_from_storage(
        "community_reports", context.output_storage
    )

    entity_emb = None
    textunit_emb = None
    community_emb = None

    entity_emb_name = f"embeddings.{entity_description_embedding}"
    textunit_emb_name = f"embeddings.{text_unit_text_embedding}"
    community_emb_name = f"embeddings.{community_full_content_embedding}"

    if await storage_has_table(entity_emb_name, context.output_storage):
        entity_emb = await load_table_from_storage(
            entity_emb_name, context.output_storage
        )
    if await storage_has_table(textunit_emb_name, context.output_storage):
        textunit_emb = await load_table_from_storage(
            textunit_emb_name, context.output_storage
        )
    if await storage_has_table(community_emb_name, context.output_storage):
        community_emb = await load_table_from_storage(
            community_emb_name, context.output_storage
        )

    def write_tx(tx):
        tx.run("MATCH (n) DETACH DELETE n")

        for _, d in documents.iterrows():
            tx.run(
                """
                MERGE (doc:Document {id:$id})
                SET doc.title=$title,
                    doc.creation_date=$creation_date
                """,
                {
                    "id": d["id"],
                    "title": d.get("title"),
                    "creation_date": str(d.get("creation_date")),
                },
            )

        for _, t in text_units.iterrows():
            tx.run(
                """
                MERGE (tu:TextUnit {id:$id})
                SET tu.text=$text,
                    tu.n_tokens=$n_tokens,
                    tu.human_readable_id=$human_readable_id
                """,
                {
                    "id": t["id"],
                    "text": t.get("text"),
                    "n_tokens": int(t.get("n_tokens", 0)),
                    "human_readable_id": int(t.get("human_readable_id", -1)),
                },
            )

            for doc_id in _as_list(t.get("document_ids")):
                tx.run(
                    """
                    MATCH (d:Document {id:$doc_id})
                    MATCH (tu:TextUnit {id:$tu_id})
                    MERGE (d)-[:HAS_TEXT_UNIT]->(tu)
                    """,
                    {"doc_id": doc_id, "tu_id": t["id"]},
                )

        for _, e in entities.iterrows():
            tx.run(
                """
                MERGE (ent:Entity {id:$id})
                SET ent.title=$title,
                    ent.type=$type,
                    ent.description=$description,
                    ent.frequency=$frequency,
                    ent.degree=$degree
                """,
                {
                    "id": e["id"],
                    "title": e.get("title"),
                    "type": e.get("type"),
                    "description": e.get("description"),
                    "frequency": int(e.get("frequency", 0)),
                    "degree": int(e.get("degree", 0)),
                },
            )

        for _, r in relationships.iterrows():
            tx.run(
                """
                MATCH (a:Entity {title:$source})
                MATCH (b:Entity {title:$target})
                MERGE (a)-[rel:RELATED_TO]->(b)
                SET rel.weight=$weight,
                    rel.description=$description
                """,
                {
                    "source": r["source"],
                    "target": r["target"],
                    "weight": float(r.get("weight", 1.0)),
                    "description": r.get("description"),
                },
            )

        for _, e in entities.iterrows():
            for tu_id in _as_list(e.get("text_unit_ids")):
                tx.run(
                    """
                    MATCH (tu:TextUnit {id:$tu_id})
                    MATCH (ent:Entity {id:$ent_id})
                    MERGE (tu)-[:MENTIONS]->(ent)
                    """,
                    {"tu_id": tu_id, "ent_id": e["id"]},
                )

        for _, c in communities.iterrows():
            tx.run(
                """
                MERGE (com:Community {id:$id})
                SET com.human_readable_id=$hid,
                    com.level=$level,
                    com.title=$title,
                    com.summary=$summary
                """,
                {
                    "id": c["id"],
                    "hid": int(c.get("human_readable_id", -1)),
                    "level": int(c.get("level", 0)),
                    "title": c.get("title"),
                    "summary": c.get("summary"),
                },
            )

            for ent_id in _as_list(c.get("entity_ids")):
                tx.run(
                    """
                    MATCH (com:Community {id:$cid})
                    MATCH (ent:Entity {id:$eid})
                    MERGE (com)-[:HAS_MEMBER]->(ent)
                    """,
                    {"cid": c["id"], "eid": ent_id},
                )

        for _, rep in community_reports.iterrows():
            tx.run(
                """
                MERGE (cr:CommunityReport {id:$id})
                SET cr.community=$community,
                    cr.full_content=$full_content,
                    cr.findings_json=$findings
                """,
                {
                    "id": rep["id"],
                    "community": rep.get("community"),
                    "full_content": rep.get("full_content"),
                    "findings": json.dumps(rep.get("findings", [])),
                },
            )

            tx.run(
                """
                MATCH (com:Community {human_readable_id:$hid})
                MATCH (cr:CommunityReport {id:$rid})
                MERGE (com)-[:HAS_REPORT]->(cr)
                """,
                {
                    "hid": int(rep.get("community", 0)),
                    "rid": rep["id"],
                },
            )

        if entity_emb is not None:
            for _, row in entity_emb.iterrows():
                tx.run(
                    """
                    MATCH (e:Entity {id:$id})
                    SET e.embedding=$emb
                    """,
                    {"id": row["id"], "emb": row["embedding"]},
                )

        if textunit_emb is not None:
            for _, row in textunit_emb.iterrows():
                tx.run(
                    """
                    MATCH (t:TextUnit {id:$id})
                    SET t.embedding=$emb
                    """,
                    {"id": row["id"], "emb": row["embedding"]},
                )

        if community_emb is not None:
            for _, row in community_emb.iterrows():
                tx.run(
                    """
                    MATCH (cr:CommunityReport {id:$id})
                    SET cr.embedding=$emb
                    """,
                    {"id": row["id"], "emb": row["embedding"]},
                )

    with driver.session() as session:
        session.execute_write(write_tx)

    driver.close()
    logger.info("Workflow completed: export_to_neo4j_full")
    return WorkflowFunctionOutput(result=None)
