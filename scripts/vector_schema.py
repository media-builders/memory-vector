from __future__ import annotations

import pyarrow as pa

VECTOR_SIZE = 384
SCALAR_STRING_FIELDS = [
    'chunk_id',
    'agent_id',
    'department',
    'workspace_path',
    'file_path',
    'source_file_path',
    'file_type',
    'date',
    'timestamp',
    'title',
    'text',
    'source_type',
    'repo_path',
    'repo_rel_path',
    'commit_sha',
    'author_name',
    'author_email',
    'commit_subject',
    'commit_body',
]
LIST_STRING_FIELDS = ['heading_path', 'changed_files']
INT_FIELDS = ['text_length', 'files_changed', 'insertions', 'deletions']


def memory_chunk_schema() -> pa.Schema:
    return pa.schema([
        pa.field('chunk_id', pa.string()),
        pa.field('agent_id', pa.string()),
        pa.field('department', pa.string()),
        pa.field('workspace_path', pa.string()),
        pa.field('file_path', pa.string()),
        pa.field('source_file_path', pa.string()),
        pa.field('file_type', pa.string()),
        pa.field('date', pa.string()),
        pa.field('timestamp', pa.string()),
        pa.field('heading_path', pa.list_(pa.string())),
        pa.field('title', pa.string()),
        pa.field('text', pa.string()),
        pa.field('text_length', pa.int64()),
        pa.field('source_type', pa.string()),
        pa.field('repo_path', pa.string()),
        pa.field('repo_rel_path', pa.string()),
        pa.field('commit_sha', pa.string()),
        pa.field('author_name', pa.string()),
        pa.field('author_email', pa.string()),
        pa.field('commit_subject', pa.string()),
        pa.field('commit_body', pa.string()),
        pa.field('changed_files', pa.list_(pa.string())),
        pa.field('files_changed', pa.int64()),
        pa.field('insertions', pa.int64()),
        pa.field('deletions', pa.int64()),
        pa.field('vector', pa.list_(pa.float32(), VECTOR_SIZE)),
    ])


def normalize_row(row: dict) -> dict:
    normalized = dict(row)

    for field in SCALAR_STRING_FIELDS:
        normalized.setdefault(field, None)

    for field in LIST_STRING_FIELDS:
        value = normalized.get(field)
        if value is None:
            normalized[field] = None
        elif isinstance(value, list):
            normalized[field] = value
        else:
            normalized[field] = [str(value)]

    for field in INT_FIELDS:
        value = normalized.get(field)
        normalized[field] = int(value) if value is not None else None

    vector = normalized.get('vector')
    if vector is not None:
        normalized['vector'] = [float(v) for v in vector]
    else:
        normalized['vector'] = None

    return normalized


def normalize_rows(rows: list[dict]) -> list[dict]:
    return [normalize_row(row) for row in rows]
