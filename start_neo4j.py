# Copyright (c) 2024 Microsoft Corporation.
# Licensed under the MIT License

"""Helper script to start Neo4j using Docker."""

import os
import subprocess
import sys
from pathlib import Path
from dotenv import load_dotenv  # type: ignore[import-untyped]

# Load .env to get password
repo_root = Path(__file__).parent.resolve()
env_path = repo_root / ".env"
if env_path.exists():
    load_dotenv(env_path, override=True)
    with env_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                key, value = key.strip(), value.strip().strip('"').strip("'")
                if value:
                    os.environ[key] = value

password = os.getenv("NEO4J_PASSWORD", "testpassword")
container_name = "graphrag-neo4j"

print("=" * 60)
print("Starting Neo4j with Docker")
print("=" * 60)

# Check if container already exists
try:
    result = subprocess.run(
        ["docker", "ps", "-a", "--filter", f"name={container_name}", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        check=False,
        shell=False
    )
    if container_name in result.stdout:
        print(f"\n[INFO] Container '{container_name}' exists")
        # Check if running
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={container_name}", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            check=False,
            shell=False
        )
        if container_name in result.stdout:
            print(f"[OK] Neo4j is already running!")
            sys.exit(0)
        else:
            print(f"[INFO] Starting existing container...")
            subprocess.run(["docker", "start", container_name], check=True, shell=False)
            print(f"[OK] Neo4j started!")
            sys.exit(0)
except Exception as e:
    print(f"[WARN] Could not check existing containers: {e}")

# Create and start new container
print(f"\n[INFO] Creating Neo4j container...")
print(f"  Container name: {container_name}")
print(f"  Port: 7687 (Bolt), 7474 (HTTP)")
print(f"  Password: {password[:3]}...")

try:
    subprocess.run([
        "docker", "run", "-d",
        "--name", container_name,
        "-p", "7687:7687",  # Bolt protocol
        "-p", "7474:7474",  # HTTP
        "-e", f"NEO4J_AUTH=neo4j/{password}",
        "-e", "NEO4J_PLUGINS=[\"apoc\"]",
        "neo4j:latest"
    ], check=True, shell=False)
    print(f"\n[SUCCESS] Neo4j container created and started!")
    print(f"\n[INFO] Neo4j is starting up (this may take 30-60 seconds)...")
    print(f"  - Bolt: bolt://localhost:7687")
    print(f"  - Browser: http://localhost:7474")
    print(f"  - Username: neo4j")
    print(f"  - Password: {password}")
    print(f"\n[INFO] Wait a moment, then run: python check_neo4j.py")
    
except subprocess.CalledProcessError as e:
    print(f"\n[ERROR] Failed to start Neo4j container")
    print(f"  Error: {e}")
    print(f"\n[Troubleshooting]")
    print(f"  1. Is Docker Desktop running?")
    print(f"  2. Try: docker ps (to verify Docker is working)")
    print(f"  3. Manual start: docker run -d --name {container_name} -p 7687:7687 -p 7474:7474 -e NEO4J_AUTH=neo4j/{password} neo4j:latest")
    sys.exit(1)
except FileNotFoundError:
    print(f"\n[ERROR] Docker command not found!")
    print(f"  Install Docker Desktop from: https://www.docker.com/products/docker-desktop")
    sys.exit(1)
