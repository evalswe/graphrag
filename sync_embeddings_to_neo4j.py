import os
import numpy as np
from neo4j import GraphDatabase
import lancedb

# ===========================
# CONFIG
# ===========================
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# your GraphRAG output folder
OUTPUT_DIR = os.getenv("GRAPHRAG_OUTPUT", "output")

# LanceDB path created by graphrag indexing
LANCEDB_DIR = os.path.join(OUTPUT_DIR, "lancedb")

# table that contains embeddings for text units
TEXTUNIT_TABLE = "default-text_unit-text"


def chunk_list(lst, chunk_size=200):
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]


def load_textunit_embeddings():
    """
    Reads embeddings from output/lancedb/default-text_unit-text.lance
    Returns list of dicts: [{"id": "...", "embedding": [...]}, ...]
    """
    db = lancedb.connect(LANCEDB_DIR)

    if TEXTUNIT_TABLE not in db.table_names():
        raise RuntimeError(
            f"Table '{TEXTUNIT_TABLE}' not found in {LANCEDB_DIR}. "
            f"Available: {db.table_names()}"
        )

    table = db.open_table(TEXTUNIT_TABLE)
    df = table.to_pandas()  # columns: id, embedding

    rows = []
    for _, r in df.iterrows():
        emb = r["embedding"]
        # ensure plain python list
        emb_list = np.array(emb, dtype=np.float32).tolist()
        rows.append({"id": r["id"], "embedding": emb_list})
    return rows


def write_embeddings_to_neo4j(driver, rows):
    """
    Writes embedding vectors into Neo4j TextUnit nodes.
    Assumes TextUnit nodes already exist with same id property.
    """
    cypher = """
    UNWIND $rows AS row
    MATCH (t:TextUnit {id: row.id})
    SET t.embedding = row.embedding
    RETURN count(t) AS updated
    """

    with driver.session() as session:
        for batch in chunk_list(rows, 200):
            result = session.run(cypher, rows=batch).single()
            print("Batch updated:", result["updated"])


def create_vector_index(driver, dims: int):
    """
    Creates Neo4j vector index for TextUnit embeddings.
    """
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
        print("✅ Vector index created/exists: textunit_embedding_index")


def check_embedding_counts(driver):
    cypher = """
    MATCH (t:TextUnit)
    RETURN count(t) AS total, count(t.embedding) AS withEmbedding;
    """
    with driver.session() as session:
        rec = session.run(cypher).single()
        print("TextUnits:", rec["total"], "With embedding:", rec["withEmbedding"])


def main():
    print("Reading embeddings from:", LANCEDB_DIR)
    rows = load_textunit_embeddings()
    print("Total embeddings found:", len(rows))

    if not rows:
        raise RuntimeError("No embeddings found. Indexing might not have produced embeddings.")

    # infer dims
    dims = len(rows[0]["embedding"])
    print("Embedding dimensions:", dims)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    print("Writing embeddings into Neo4j...")
    write_embeddings_to_neo4j(driver, rows)

    print("Creating vector index...")
    create_vector_index(driver, dims)

    print("Verifying counts...")
    check_embedding_counts(driver)

    driver.close()
    print("✅ Done")


if __name__ == "__main__":
    main()
