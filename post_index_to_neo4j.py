import os
import json
import pandas as pd
import numpy as np
from neo4j import GraphDatabase

# ---------------- CONFIG ---------------- #
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

OUTPUT_DIR = "output"
# ---------------------------------------- #


def load_parquet(path):
    if not os.path.exists(path):
        print(f"⚠️ Not found: {path}")
        return None
    print(f"✅ Reading {path}")
    return pd.read_parquet(path)


def ensure_list_embedding(x):
    """
    Neo4j expects embedding as list[float]
    """
    if x is None:
        return None
    if isinstance(x, list):
        return [float(i) for i in x]
    if isinstance(x, np.ndarray):
        return x.astype(float).tolist()
    return None


def safe_list(value):
    if value is None:
        return []
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (list, tuple, set)):
        return list(value)
    if isinstance(value, float) and pd.isna(value):
        return []
    try:
        if pd.isna(value):
            return []
    except ValueError:
        return []
    return []


def to_jsonable(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    return value


class Neo4jLoader:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
        )

    def close(self):
        self.driver.close()

    def run_query(self, query, params=None):
        with self.driver.session() as session:
            session.run(query, params or {})

    def clear_db(self):
        print("⚠️ Clearing Neo4j DB...")
        self.run_query("MATCH (n) DETACH DELETE n")

    def create_constraints(self):
        print("✅ Creating constraints...")
        self.drop_index_for_label_property("Entity", "id")
        self.drop_index_for_label_property("Document", "id")
        self.drop_index_for_label_property("TextUnit", "id")
        self.drop_index_for_label_property("Community", "id")
        self.drop_index_for_label_property("CommunityReport", "id")
        self.run_query(
            "CREATE CONSTRAINT IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE;"
        )
        self.run_query(
            "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE;"
        )
        self.run_query(
            "CREATE CONSTRAINT IF NOT EXISTS FOR (t:TextUnit) REQUIRE t.id IS UNIQUE;"
        )
        self.run_query(
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Community) REQUIRE c.id IS UNIQUE;"
        )
        self.run_query(
            "CREATE CONSTRAINT IF NOT EXISTS FOR (r:CommunityReport) REQUIRE r.id IS UNIQUE;"
        )

    def drop_index_for_label_property(self, label, prop):
        with self.driver.session() as session:
            result = session.run(
                """
                SHOW INDEXES
                YIELD name, labelsOrTypes, properties, owningConstraint
                WHERE labelsOrTypes = [$label] AND properties = [$prop]
                RETURN name, owningConstraint
                """,
                {"label": label, "prop": prop},
            )
            rows = list(result)

        for row in rows:
            owning = row["owningConstraint"]
            if owning:
                self.run_query(f"DROP CONSTRAINT {owning} IF EXISTS")
            self.run_query(f"DROP INDEX {row['name']} IF EXISTS")

    def create_vector_index(self, label, prop, dims, index_name):
        print(f"✅ Creating vector index: {index_name}")
        self.run_query(
            f"""
        CREATE VECTOR INDEX {index_name} IF NOT EXISTS
        FOR (n:{label})
        ON (n.{prop})
        OPTIONS {{indexConfig: {{
          `vector.dimensions`: {dims},
          `vector.similarity_function`: 'cosine'
        }}}};
        """
        )

    # ---------------- LOAD NODES ---------------- #

    def load_entities(self, df):
        if df is None or df.empty:
            return
        print("✅ Loading Entities...")
        query = """
        UNWIND $rows AS row
        MERGE (e:Entity {id: row.id})
        SET e.title = row.title,
            e.type = row.type,
            e.description = row.description,
            e.frequency = row.frequency,
            e.degree = row.degree,
            e.human_readable_id = row.human_readable_id
        """
        rows = df.to_dict("records")
        self.run_query(query, {"rows": rows})

    def load_documents(self, df):
        if df is None or df.empty:
            return
        print("✅ Loading Documents...")
        query = """
        UNWIND $rows AS row
        MERGE (d:Document {id: row.id})
        SET d.title = row.title,
            d.text = row.text,
            d.creation_date = row.creation_date
        """
        rows = df.to_dict("records")
        self.run_query(query, {"rows": rows})

    def load_textunits(self, df):
        if df is None or df.empty:
            return
        print("✅ Loading TextUnits...")
        query = """
        UNWIND $rows AS row
        MERGE (t:TextUnit {id: row.id})
        SET t.text = row.text,
            t.n_tokens = row.n_tokens,
            t.human_readable_id = row.human_readable_id
        """
        rows = df.to_dict("records")
        self.run_query(query, {"rows": rows})

    def load_relationships(self, df):
        if df is None or df.empty:
            return
        print("✅ Loading Relationships...")
        query = """
        UNWIND $rows AS row
        MATCH (s:Entity {title: row.source})
        MATCH (t:Entity {title: row.target})
        MERGE (s)-[r:RELATED_TO]->(t)
        SET r.weight = row.weight,
            r.description = row.description
        """
        rows = df.to_dict("records")
        self.run_query(query, {"rows": rows})

    def load_communities(self, df):
        if df is None or df.empty:
            return
        print("✅ Loading Communities...")
        query = """
        UNWIND $rows AS row
        MERGE (c:Community {id: row.id})
        SET c.human_readable_id = row.human_readable_id,
            c.level = row.level,
            c.title = row.title,
            c.summary = row.summary
        """
        rows = df.to_dict("records")
        self.run_query(query, {"rows": rows})

    def load_community_reports(self, df):
        if df is None or df.empty:
            return
        print("✅ Loading Community Reports...")
        query = """
        UNWIND $rows AS row
        MERGE (r:CommunityReport {id: row.id})
        SET r.full_content = row.full_content,
            r.findings_json = row.findings_json,
            r.community = row.community,
            r.human_readable_id = row.human_readable_id
        """
        rows = []
        for _, row in df.iterrows():
            rows.append(
                {
                    "id": row["id"],
                    "full_content": row.get("full_content"),
                    "findings_json": json.dumps(to_jsonable(row.get("findings", []))),
                    "community": row.get("community"),
                    "human_readable_id": row.get("human_readable_id"),
                }
            )
        self.run_query(query, {"rows": rows})

    # ---------------- LOAD RELATIONSHIPS ---------------- #

    def link_documents_textunits(self, df):
        if df is None or df.empty:
            return
        print("✅ Linking Documents -> TextUnits...")
        for _, t in df.iterrows():
            for doc_id in safe_list(t.get("document_ids")):
                self.run_query(
                    """
                    MATCH (d:Document {id:$doc_id})
                    MATCH (t:TextUnit {id:$tu_id})
                    MERGE (d)-[:HAS_TEXT_UNIT]->(t)
                    """,
                    {"doc_id": doc_id, "tu_id": t["id"]},
                )

    def link_textunits_entities(self, df):
        if df is None or df.empty:
            return
        print("✅ Linking TextUnits -> Entities...")
        for _, e in df.iterrows():
            for tu_id in safe_list(e.get("text_unit_ids")):
                self.run_query(
                    """
                    MATCH (t:TextUnit {id:$tu_id})
                    MATCH (e:Entity {id:$ent_id})
                    MERGE (t)-[:MENTIONS]->(e)
                    """,
                    {"tu_id": tu_id, "ent_id": e["id"]},
                )

    def link_communities_entities(self, df):
        if df is None or df.empty:
            return
        print("✅ Linking Communities -> Entities...")
        for _, c in df.iterrows():
            for ent_id in safe_list(c.get("entity_ids")):
                self.run_query(
                    """
                    MATCH (c:Community {id:$cid})
                    MATCH (e:Entity {id:$eid})
                    MERGE (c)-[:HAS_MEMBER]->(e)
                    """,
                    {"cid": c["id"], "eid": ent_id},
                )

    def link_communities_reports(self, df):
        if df is None or df.empty:
            return
        print("✅ Linking Communities -> Reports...")
        for _, rep in df.iterrows():
            self.run_query(
                """
                MATCH (c:Community {human_readable_id:$hid})
                MATCH (r:CommunityReport {id:$rid})
                MERGE (c)-[:HAS_REPORT]->(r)
                """,
                {"hid": int(rep.get("community", 0)), "rid": rep["id"]},
            )

    # ---------------- LOAD EMBEDDINGS ---------------- #

    def update_embeddings(self, df, label, id_col="id", emb_col="embedding"):
        if df is None or df.empty:
            return None

        print(f"✅ Loading embeddings into {label}...")
        query = f"""
        UNWIND $rows AS row
        MATCH (n:{label} {{id: row.id}})
        SET n.embedding = row.embedding
        """
        rows = []
        for _, row in df.iterrows():
            emb = ensure_list_embedding(row[emb_col])
            if emb:
                rows.append({"id": row[id_col], "embedding": emb})

        if rows:
            self.run_query(query, {"rows": rows})
            dims = len(rows[0]["embedding"])
            return dims
        return None


def main():
    loader = Neo4jLoader()

    loader.create_constraints()

    entities = load_parquet(os.path.join(OUTPUT_DIR, "entities.parquet"))
    relationships = load_parquet(os.path.join(OUTPUT_DIR, "relationships.parquet"))
    documents = load_parquet(os.path.join(OUTPUT_DIR, "documents.parquet"))
    text_units = load_parquet(os.path.join(OUTPUT_DIR, "text_units.parquet"))
    communities = load_parquet(os.path.join(OUTPUT_DIR, "communities.parquet"))
    community_reports = load_parquet(
        os.path.join(OUTPUT_DIR, "community_reports.parquet")
    )

    loader.load_entities(entities)
    loader.load_relationships(relationships)
    loader.load_documents(documents)
    loader.load_textunits(text_units)
    loader.load_communities(communities)
    loader.load_community_reports(community_reports)

    loader.link_documents_textunits(text_units)
    loader.link_textunits_entities(entities)
    loader.link_communities_entities(communities)
    loader.link_communities_reports(community_reports)

    entity_emb = load_parquet(
        os.path.join(OUTPUT_DIR, "embeddings.entity.description.parquet")
    )
    textunit_emb = load_parquet(
        os.path.join(OUTPUT_DIR, "embeddings.text_unit.text.parquet")
    )
    comm_emb = load_parquet(
        os.path.join(OUTPUT_DIR, "embeddings.community.full_content.parquet")
    )

    dims = loader.update_embeddings(textunit_emb, "TextUnit")
    if dims:
        loader.create_vector_index("TextUnit", "embedding", dims, "textunit_embedding_index")

    dims = loader.update_embeddings(entity_emb, "Entity")
    if dims:
        loader.create_vector_index("Entity", "embedding", dims, "entity_embedding_index")

    dims = loader.update_embeddings(comm_emb, "CommunityReport")
    if dims:
        loader.create_vector_index(
            "CommunityReport", "embedding", dims, "community_embedding_index"
        )

    print("🎉 Neo4j now has full GraphRAG data + embeddings + vector search enabled!")
    loader.close()


if __name__ == "__main__":
    main()
