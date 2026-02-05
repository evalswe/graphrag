import pandas as pd
from neo4j import GraphDatabase

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "password"

OUTPUT_DIR = "output"


def load_entities(session, entities_df):
    query = """
    UNWIND $rows AS row
    MERGE (e:Entity {id: row.id})
    SET e.title = row.title,
        e.type = row.type,
        e.description = row.description,
        e.human_readable_id = row.human_readable_id,
        e.frequency = row.frequency,
        e.degree = row.degree
    """
    session.run(query, rows=entities_df.to_dict("records"))


def load_relationships(session, rels_df):
    query = """
    UNWIND $rows AS row
    MATCH (s:Entity {title: row.source})
    MATCH (t:Entity {title: row.target})
    MERGE (s)-[r:RELATED_TO]->(t)
    SET r.weight = row.weight,
        r.description = row.description
    """
    session.run(query, rows=rels_df.to_dict("records"))


def main():
    entities_path = f"{OUTPUT_DIR}/entities.parquet"
    rels_path = f"{OUTPUT_DIR}/relationships.parquet"

    entities_df = pd.read_parquet(entities_path)
    rels_df = pd.read_parquet(rels_path)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))

    with driver.session() as session:
        # cleanup old graph (optional)
        session.run("MATCH (n) DETACH DELETE n")

        load_entities(session, entities_df)
        load_relationships(session, rels_df)

        # create indexes
        session.run("CREATE INDEX entity_id IF NOT EXISTS FOR (e:Entity) ON (e.id)")
        session.run("CREATE INDEX entity_title IF NOT EXISTS FOR (e:Entity) ON (e.title)")

    driver.close()
    print("✅ Loaded GraphRAG output into Neo4j successfully!")


if __name__ == "__main__":
    main()
