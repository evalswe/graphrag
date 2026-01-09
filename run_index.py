# Copyright (c) 2024 Microsoft Corporation.
# Licensed under the MIT License

"""Script to run GraphRAG indexing pipeline."""

import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv  # type: ignore[import-untyped]

# Fix Unicode encoding on Windows
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    else:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from graphrag.api.index import build_index
from graphrag.config.load_config import load_config

repo_root = Path(__file__).parent.resolve()
env_path = repo_root / ".env"

# Load .env file
if not env_path.exists():
    print("⚠️ .env file not found")
    sys.exit(1)

load_dotenv(env_path, override=True)

# Manually parse .env to ensure all keys are loaded
with env_path.open("r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if value:
                os.environ[key] = value

# Set GRAPHRAG_API_KEY from OPENAI_API_KEY if needed
if not os.getenv("GRAPHRAG_API_KEY") and (openai_key := os.getenv("OPENAI_API_KEY")):
    os.environ["GRAPHRAG_API_KEY"] = openai_key

# Validate API keys
openai_key = os.getenv("GRAPHRAG_API_KEY") or os.getenv("OPENAI_API_KEY")
gemini_key = os.getenv("GEMINI_API_KEY")

print("\n[API Key Status]")
print(f"  {'✓' if openai_key else '✗'} GRAPHRAG_API_KEY: {'loaded' if openai_key else 'not found'}")
print(f"  {'✓' if gemini_key else '✗'} GEMINI_API_KEY: {'loaded' if gemini_key else 'not found'}")

if not openai_key and not gemini_key:
    print("\n[ERROR] No API keys found. Set GRAPHRAG_API_KEY or GEMINI_API_KEY in .env")
    sys.exit(1)

# Load configuration
print("\n[INFO] Loading configuration...")
try:
    config = load_config(root_dir=repo_root, config_filepath=None)
except Exception as e:
    print(f"[ERROR] Failed to load configuration: {e}")
    sys.exit(1)

# Check input directory
input_dir = repo_root / "input" / "documents"
files = list(input_dir.glob("*.txt")) if input_dir.exists() else []
print(f"[INFO] Found {len(files)} input file(s)")

# Run indexing
print("\n[INFO] Starting indexing pipeline...\n")
try:
    results = asyncio.run(build_index(config, verbose=True))
    has_errors = any(r.errors and len(r.errors) > 0 for r in results)
    
    print("\n" + "=" * 60)
    print("[WARNING] Indexing completed with errors!" if has_errors else "[SUCCESS] Indexing completed!")
    print("=" * 60)
    
    for result in results:
        status = "ERROR" if result.errors else "OK"
        print(f"  - {result.workflow}: {status}")
        if result.errors:
            for i, error in enumerate(result.errors, 1):
                print(f"\n    Error {i}: {type(error).__name__}: {error}")
                import traceback
                for line in traceback.format_exception(type(error), error, error.__traceback__):
                    print(f"      {line.strip()}")
except KeyboardInterrupt:
    print("\n[INFO] Interrupted by user")
    sys.exit(1)
except Exception as e:
    print(f"\n[ERROR] Indexing failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
