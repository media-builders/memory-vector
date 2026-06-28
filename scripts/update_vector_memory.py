from pathlib import Path
import json
import hashlib
import os
import shutil
import sys
import lancedb
from sentence_transformers import SentenceTransformer
from vector_schema import memory_chunk_schema, normalize_rows

# Resolve workspace root from env var or command-line arg, fallback to default
_resolved_root = os.environ.get("MEMORY_WORKSPACE_ROOT")
if not _resolved_root and len(sys.argv) > 1:
    _resolved_root = sys.argv[1]
WORKSPACE_ROOT = Path(_resolved_root) if _resolved_root else Path.home() / ".openclaw" / "workspace"


def resolve_path(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else root / path


_index_path = os.environ.get("MEMORY_INDEX_PATH")
if not _index_path and len(sys.argv) > 2:
    _index_path = sys.argv[2]
VECTOR_DIR = resolve_path(WORKSPACE_ROOT, _index_path or "plugins/memory-vector/vector")
CHUNKS = VECTOR_DIR / 'chunks.jsonl'
INDEX = VECTOR_DIR / 'index.json'
EMBEDDINGS = VECTOR_DIR / 'embeddings.jsonl'
MANIFEST = VECTOR_DIR / 'manifest.json'
STATE = VECTOR_DIR / 'state.json'
LANCEDB_DIR = VECTOR_DIR / 'lancedb'
TABLE_NAME = 'memory_chunks'
MODEL_NAME = 'sentence-transformers/all-MiniLM-L6-v2'
BATCH_SIZE = 32


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text())


def load_chunks():
    rows = []
    with CHUNKS.open() as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def row_source_file_path(row):
    return row.get('source_file_path') or row.get('file_path')


def main():
    index = load_json(INDEX, [])
    prev_state = load_json(STATE, {'files': {}, 'repos': {}})
    prev_files = prev_state.get('files', {})
    prev_repos = prev_state.get('repos', {})

    current_files = {}
    current_repos = {}
    changed_sources = set()

    for item in index:
        source_type = item.get('source_type')
        if source_type == 'workspace_markdown':
            path = Path(item['file_path'])
            digest = file_sha256(path)
            current_files[str(path)] = {
                'sha256': digest,
                'chunk_count': item.get('chunk_count', 0),
                'file_type': item.get('file_type'),
                'source_type': source_type,
            }
            prev = prev_files.get(str(path), {})
            if prev.get('sha256') != digest or prev.get('chunk_count') != item.get('chunk_count', 0):
                changed_sources.add(str(path))
        elif source_type == 'git_commit':
            repo_path = item['repo_path']
            current_repos[repo_path] = {
                'head_sha': item.get('head_sha'),
                'commit_count': item.get('commit_count', 0),
                'source_type': source_type,
                'repo_rel_path': item.get('repo_rel_path'),
            }

    for repo_path, repo_state in current_repos.items():
        prev = prev_repos.get(repo_path, {})
        if prev.get('head_sha') != repo_state.get('head_sha') or prev.get('commit_count') != repo_state.get('commit_count', 0):
            changed_sources.add(f'{repo_path}/.git')

    removed_files = set(prev_files) - set(current_files)
    removed_repos = set(prev_repos) - set(current_repos)
    changed_sources |= removed_files
    changed_sources |= {f'{repo}/.git' for repo in removed_repos}

    rows = load_chunks()
    old_rows = []
    if EMBEDDINGS.exists():
        with EMBEDDINGS.open() as f:
            for line in f:
                if line.strip():
                    old_rows.append(json.loads(line))

    kept_rows = [
        r for r in old_rows
        if row_source_file_path(r) not in changed_sources
        and (
            (r.get('source_type') == 'workspace_markdown' and row_source_file_path(r) in current_files)
            or (r.get('source_type') == 'git_commit' and row_source_file_path(r) in {f'{repo}/.git' for repo in current_repos})
        )
    ]
    new_chunks = [r for r in rows if row_source_file_path(r) in changed_sources]

    embedded_new_rows = []
    if new_chunks:
        model = SentenceTransformer(MODEL_NAME)
        vectors = model.encode([r['text'] for r in new_chunks], batch_size=BATCH_SIZE, show_progress_bar=True, normalize_embeddings=True)
        for chunk, vector in zip(new_chunks, vectors):
            rec = dict(chunk)
            rec['vector'] = vector.tolist()
            embedded_new_rows.append(rec)

    changed_chunk_ids = {r['chunk_id'] for r in new_chunks}
    kept_rows = [r for r in kept_rows if r.get('chunk_id') not in changed_chunk_ids]

    final_rows = normalize_rows(kept_rows + embedded_new_rows)

    with EMBEDDINGS.open('w') as out:
        for row in final_rows:
            out.write(json.dumps(row) + '\n')

    if LANCEDB_DIR.exists():
        shutil.rmtree(LANCEDB_DIR)
    db = lancedb.connect(str(LANCEDB_DIR))
    db.create_table(TABLE_NAME, data=final_rows, schema=memory_chunk_schema(), mode='overwrite')

    STATE.write_text(json.dumps({'files': current_files, 'repos': current_repos}, indent=2))

    manifest = load_json(MANIFEST, {})
    manifest.update({
        'embedding_model': MODEL_NAME,
        'embeddings_built': True,
        'lancedb_table': TABLE_NAME,
        'lancedb_path': str(LANCEDB_DIR),
        'embedded_chunk_count': len(final_rows),
        'incremental_last_changed_sources': len(changed_sources),
        'incremental_last_new_chunks': len(new_chunks),
        'tracked_markdown_file_count': len(current_files),
        'tracked_git_repo_count': len(current_repos),
    })
    MANIFEST.write_text(json.dumps(manifest, indent=2))

    print(f'changed_sources={len(changed_sources)}')
    print(f'new_or_updated_chunks={len(new_chunks)}')
    print(f'total_embedded_rows={len(final_rows)}')


if __name__ == '__main__':
    main()
