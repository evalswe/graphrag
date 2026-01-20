import os
import numpy as np
from neo4j import GraphDatabase
import lancedb


def _chunk_list(items, chunk_size=200):
    for i in range(0, len(items), chunk_size):
        yield items[i:i + chunk_size]


def _load_textunit_embeddings(lancedb_dir, table_name):
    db = lancedb.connect(lancedb_dir)

    if table_name not in db.table_names():
        raise RuntimeError(
            f"Table '{table_name}' not found in {lancedb_dir}. "
            f"Available: {db.table_names()}"
        )

    table = db.open_table(table_name)
    df = table.to_pandas()

    rows = []
    for _, r in df.iterrows():
        emb = r["embedding"]
        emb_list = np.array(emb, dtype=np.float32).tolist()
        rows.append({"id": r["id"], "embedding": emb_list})
    return rows


def write_textunit_embeddings(driver, rows):
    cypher = """
    UNWIND $rows AS row
    MATCH (t:TextUnit {id: row.id})
    SET t.embedding = row.embedding
    """
    with driver.session() as session:
        for batch in _chunk_list(rows, 200):
            session.run(cypher, rows=batch)


def create_vector_index(driver, dims):
    cypher = f"""
    CREATE VECTOR INDEX textunit_embedding_index IF NOT EXISTS
    FOR (t:TextUnit)
    ON (t.embedding)
    OPTIONS {{
      indexConfig: {{
        `vector.dimensions`: {dims},
        `vector.similarity_function`: 'cosine'
      }}
    }};
    """
    with driver.session() as session:
        session.run(cypher)


def sync_textunit_embeddings_to_neo4j(
    output_dir,
    uri=None,
    user=None,
    password=None,
    lancedb_table="default-text_unit-text",
):
    lancedb_dir = os.path.join(output_dir, "lancedb")
    rows = _load_textunit_embeddings(lancedb_dir, lancedb_table)
    if not rows:
        raise RuntimeError("No embeddings found in LanceDB.")

    dims = len(rows[0]["embedding"])

    uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = user or os.getenv("NEO4J_USER", "neo4j")
    password = password or os.getenv("NEO4J_PASSWORD", "password")

    driver = GraphDatabase.driver(uri, auth=(user, password))
    write_textunit_embeddings(driver, rows)
    create_vector_index(driver, dims)
    driver.close()
