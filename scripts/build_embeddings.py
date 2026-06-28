from pathlib import Path
import json
import os
import shutil
import sys
import lancedb
from sentence_transformers import SentenceTransformer
from vector_schema import memory_chunk_schema, normalize_rows


def resolve_path(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else root / path


_resolved_root = os.environ.get("MEMORY_WORKSPACE_ROOT")
if not _resolved_root and len(sys.argv) > 1:
    _resolved_root = sys.argv[1]
WORKSPACE_ROOT = Path(_resolved_root).expanduser() if _resolved_root else Path.home() / ".openclaw" / "workspace"

_index_path = os.environ.get("MEMORY_INDEX_PATH")
if not _index_path and len(sys.argv) > 2:
    _index_path = sys.argv[2]
VECTOR_DIR = resolve_path(WORKSPACE_ROOT, _index_path or "plugins/memory-vector/vector")
CHUNKS = VECTOR_DIR / 'chunks.jsonl'
EMBEDDINGS = VECTOR_DIR / 'embeddings.jsonl'
LANCEDB_DIR = VECTOR_DIR / 'lancedb'
TABLE_NAME = 'memory_chunks'
MODEL_NAME = 'sentence-transformers/all-MiniLM-L6-v2'
BATCH_SIZE = 32


def load_chunks():
    with CHUNKS.open() as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def main():
    chunks = list(load_chunks())
    if not chunks:
        raise SystemExit('No chunks found. Run ingest_memory.py first.')

    texts = [c['text'] for c in chunks]
    model = SentenceTransformer(MODEL_NAME)
    vectors = model.encode(texts, batch_size=BATCH_SIZE, show_progress_bar=True, normalize_embeddings=True)

    rows = []
    with EMBEDDINGS.open('w') as out:
        for chunk, vector in zip(chunks, vectors):
            row = dict(chunk)
            row['vector'] = vector.tolist()
            rows.append(row)
        rows = normalize_rows(rows)
        for row in rows:
            out.write(json.dumps(row) + '\n')

    if LANCEDB_DIR.exists():
        shutil.rmtree(LANCEDB_DIR)
    db = lancedb.connect(str(LANCEDB_DIR))
    db.create_table(TABLE_NAME, data=rows, schema=memory_chunk_schema(), mode='overwrite')

    manifest_path = VECTOR_DIR / 'manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest.update({
        'embedding_model': MODEL_NAME,
        'embeddings_built': True,
        'lancedb_table': TABLE_NAME,
        'lancedb_path': str(LANCEDB_DIR),
        'embedded_chunk_count': len(rows),
    })
    manifest_path.write_text(json.dumps(manifest, indent=2))

    print(f'embedded_chunks={len(rows)}')
    print(f'wrote={EMBEDDINGS}')
    print(f'lancedb={LANCEDB_DIR}')


if __name__ == '__main__':
    main()
