from pathlib import Path
import json
import hashlib
import os
import re
import subprocess
from datetime import datetime, UTC

import sys as _plugin_sys


def resolve_path(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else root / path


_workspace_root = os.environ.get("MEMORY_WORKSPACE_ROOT")
if not _workspace_root and len(_plugin_sys.argv) > 1:
    _workspace_root = _plugin_sys.argv[1]
WORKSPACE_ROOT = Path(_workspace_root).expanduser() if _workspace_root else Path.home() / ".openclaw" / "workspace"

_index_path = os.environ.get("MEMORY_INDEX_PATH")
if not _index_path and len(_plugin_sys.argv) > 2:
    _index_path = _plugin_sys.argv[2]
OUT_DIR = resolve_path(WORKSPACE_ROOT, _index_path or "plugins/memory-vector/vector")

_memory_root = os.environ.get("MEMORY_ROOT")
if not _memory_root and len(_plugin_sys.argv) > 3:
    _memory_root = _plugin_sys.argv[3]
BASE = resolve_path(WORKSPACE_ROOT, _memory_root or "company")

_memory_paths_raw = os.environ.get("MEMORY_PATHS")
if not _memory_paths_raw and len(_plugin_sys.argv) > 4:
    _memory_paths_raw = _plugin_sys.argv[4]
try:
    MEMORY_PATHS = json.loads(_memory_paths_raw) if _memory_paths_raw else []
except json.JSONDecodeError:
    MEMORY_PATHS = [_memory_paths_raw] if _memory_paths_raw else []
MEMORY_PATHS = [
    resolve_path(WORKSPACE_ROOT, item)
    for item in MEMORY_PATHS
    if isinstance(item, str) and item.strip()
]

if not BASE.exists() and not MEMORY_PATHS:
    raise SystemExit(f"memory root not found: {BASE}")

CHUNKS = OUT_DIR / 'chunks.jsonl'
MANIFEST = OUT_DIR / 'manifest.json'
INDEX = OUT_DIR / 'index.json'

HEADING_RE = re.compile(r'^(#{1,6})\s+(.*)$')
COMPANY_PATH_RE = re.compile(r'(?:^|[/\\])company[/\\]([a-z0-9-]+)(?=$|[/\\])')
AGENT_ID_RE = re.compile(r'"agent_id"\s*:\s*"([a-z0-9-]+)"')
LIVE_AGENTS = frozenset(
    d.name for d in (BASE.iterdir() if BASE.exists() else [])
    if d.is_dir() and d.name != 'brain' and (d / 'AGENTS.md').exists()
)
NON_AGENT_COMPANY_DIRS = frozenset({'brain', 'headquarters', 'knowledge', 'projects'})
KNOWN_COMPANY_DIRS = LIVE_AGENTS | NON_AGENT_COMPANY_DIRS
ALLOWED_METADATA_AGENT_IDS = LIVE_AGENTS | {'workspace', 'main', 'brain'}
REMOVED_AGENT_TOKENS = frozenset({
    'chief-of-staff',
    'engineering-dev-backend',
    'engineering-dev-frontend',
    'engineering-manager',
    'marketing-analyst',
    'marketing-campaign-specialist',
    'marketing-content-creator',
    'marketing-growth-specialist',
    'marketing-manager',
    'operations-head',
    'product-manager',
    'sales-manager',
})


def contains_removed_agent_reference(value):
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    text = text.lower()

    if any(token in text for token in REMOVED_AGENT_TOKENS):
        return True

    if LIVE_AGENTS:
        for name in COMPANY_PATH_RE.findall(text):
            if name not in KNOWN_COMPANY_DIRS:
                return True

        for name in AGENT_ID_RE.findall(text):
            if name not in ALLOWED_METADATA_AGENT_IDS:
                return True

    return False


def dept_for(agent):
    if agent in {'ceo', 'brain'}:
        return 'executive'
    if agent.startswith('design-'):
        return 'design'
    if agent.startswith('engineering-'):
        return 'engineering'
    if agent.startswith('product-'):
        return 'product'
    if agent.startswith('operations-'):
        return 'operations'
    if agent.startswith('marketing-'):
        return 'marketing'
    if agent.startswith('sales-'):
        return 'sales'
    if agent.startswith('finance-'):
        return 'finance'
    return 'other'


def discover_memory_files():
    if MEMORY_PATHS:
        return discover_configured_memory_files()

    files = []
    for d in sorted(BASE.iterdir()):
        if not d.is_dir() or not (d / 'AGENTS.md').exists():
            continue
        if d.name == 'brain':
            continue
        mem = d / 'MEMORY.md'
        if mem.exists():
            files.append(mem)
        memdir = d / 'memory'
        if memdir.exists():
            files.extend(sorted(memdir.glob('*.md')))
    return files


def is_ignored_path(path: Path):
    return any(part in {'.venv', 'node_modules', '__pycache__', '.git'} for part in path.parts)


def add_markdown_file(files, seen, path: Path):
    if not path.exists() or not path.is_file() or path.suffix.lower() != '.md':
        return
    if is_ignored_path(path):
        return
    resolved = path.resolve()
    if resolved in seen:
        return
    seen.add(resolved)
    files.append(path)


def discover_configured_memory_files():
    files = []
    seen = set()
    for target in MEMORY_PATHS:
        if not target.exists():
            continue
        if target.is_file():
            add_markdown_file(files, seen, target)
            continue

        if (target / 'AGENTS.md').exists():
            add_markdown_file(files, seen, target / 'MEMORY.md')
            memdir = target / 'memory'
            if memdir.exists():
                for path in sorted(memdir.glob('*.md')):
                    add_markdown_file(files, seen, path)
            continue

        for path in sorted(target.rglob('*.md')):
            add_markdown_file(files, seen, path)
    return files


def infer_agent_id(path: Path):
    try:
        rel = path.relative_to(BASE)
        if rel.parts:
            return rel.parts[0]
    except ValueError:
        pass

    current = path if path.is_dir() else path.parent
    for parent in [current, *current.parents]:
        if (parent / 'AGENTS.md').exists():
            return parent.name

    if path.parent.name == 'memory' and path.parent.parent.name:
        return path.parent.parent.name
    if path.name == 'MEMORY.md' and path.parent.name:
        return path.parent.name
    return 'workspace'


def infer_workspace_path(path: Path, agent: str):
    current = path if path.is_dir() else path.parent
    for parent in [current, *current.parents]:
        if (parent / 'AGENTS.md').exists():
            return str(parent)
    if agent in LIVE_AGENTS and BASE.exists():
        return str(BASE / agent)
    if path.parent.name == 'memory':
        return str(path.parent.parent)
    return str(path.parent)


def file_type_for(path: Path):
    if path.name == 'MEMORY.md':
        return 'durable'
    if path.parent.name == 'memory':
        return 'daily'
    return 'memory'


def relative_repo_path(repo: Path):
    try:
        return str(repo.relative_to(BASE))
    except ValueError:
        return str(repo)


def discover_git_repos():
    repos = []
    roots = MEMORY_PATHS if MEMORY_PATHS else [BASE]
    for root in roots:
        if not root.exists() or root.is_file():
            continue
        for git_dir in sorted(root.rglob('.git')):
            repo = git_dir.parent
            if OUT_DIR in repo.parents:
                continue
            if any(part in {'.venv', 'node_modules', '.git'} for part in repo.parts):
                continue
            repos.append(repo)
    return repos


def chunk_markdown(text):
    lines = text.splitlines()
    sections = []
    current_heading = []
    buf = []

    def flush():
        nonlocal buf, current_heading
        content = '\n'.join(buf).strip()
        # Drop heading-only sections (no body text) and prepend heading path for context
        if content:
            lines_only = content.split('\n')
            is_heading_only = all(l.startswith('#') or not l.strip() for l in lines_only)
            if not is_heading_only:
                if current_heading:
                    heading_context = ' > '.join(current_heading)
                    content = f"{heading_context}\n{content}"
                sections.append({'heading_path': current_heading.copy(), 'text': content})
        buf = []

    for line in lines:
        m = HEADING_RE.match(line)
        if m:
            flush()
            level = len(m.group(1))
            title = m.group(2).strip()
            current_heading = current_heading[:level - 1] + [title]
            buf = [line]
        else:
            buf.append(line)
    flush()

    if not sections:
        stripped = text.strip()
        if stripped:
            sections.append({'heading_path': [], 'text': stripped})

    chunks = []
    for section in sections:
        section_text = section['text'].strip()
        if len(section_text) <= 3000:
            chunks.append(section)
            continue
        paragraphs = section_text.split('\n\n')
        block = []
        size = 0
        for p in paragraphs:
            p = p.strip()
            if not p:
                continue
            add = len(p) + (2 if block else 0)
            if size + add > 3000 and block:
                chunks.append({'heading_path': section['heading_path'], 'text': '\n\n'.join(block)})
                block = [p]
                size = len(p)
            else:
                block.append(p)
                size += add
        if block:
            chunks.append({'heading_path': section['heading_path'], 'text': '\n\n'.join(block)})
    return chunks


def run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ['git', '-C', str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def repo_agent_id(repo: Path) -> str:
    try:
        rel = repo.relative_to(BASE)
        return rel.parts[0] if rel.parts else 'workspace'
    except ValueError:
        return infer_agent_id(repo)


def build_commit_chunk_text(commit):
    changed_files = commit.get('changed_files', [])
    changed_block = '\n'.join(f'- {path}' for path in changed_files[:50])
    if len(changed_files) > 50:
        changed_block += f"\n- ... and {len(changed_files) - 50} more"

    parts = [
        f"Commit {commit['commit_sha'][:12]} in {commit['repo_rel_path']}",
        f"Author: {commit['author_name']} <{commit['author_email']}>",
        f"Date: {commit['committed_at']}",
        f"Subject: {commit['subject']}",
    ]
    if commit.get('body'):
        parts.append(f"Body:\n{commit['body']}")
    parts.append(
        "Stats: "
        f"{commit.get('files_changed', 0)} files changed, "
        f"{commit.get('insertions', 0)} insertions(+), "
        f"{commit.get('deletions', 0)} deletions(-)"
    )
    if changed_block:
        parts.append(f"Changed files:\n{changed_block}")
    return '\n\n'.join(parts).strip()


def parse_numstat(repo: Path, commit_sha: str):
    stdout = run_git(repo, 'show', '--numstat', '--format=', '--no-renames', commit_sha)
    changed_files = []
    insertions = 0
    deletions = 0

    for line in stdout.splitlines():
        parts = line.split('\t')
        if len(parts) < 3:
            continue
        ins_raw, del_raw, path = parts[0], parts[1], parts[2]
        changed_files.append(path)
        if ins_raw.isdigit():
            insertions += int(ins_raw)
        if del_raw.isdigit():
            deletions += int(del_raw)

    return {
        'changed_files': changed_files,
        'files_changed': len(changed_files),
        'insertions': insertions,
        'deletions': deletions,
    }


def collect_git_commit_records():
    records = []
    repo_index = []
    for repo in discover_git_repos():
        agent_id = repo_agent_id(repo)
        department = dept_for(agent_id)
        repo_rel_path = relative_repo_path(repo)
        log_format = '%H%x1f%aI%x1f%cI%x1f%an%x1f%ae%x1f%s%x1f%b%x1e'
        try:
            raw = run_git(repo, 'log', '--date=iso-strict', f'--pretty=format:{log_format}', '--reverse')
            head_sha = run_git(repo, 'rev-parse', 'HEAD').strip()
        except subprocess.CalledProcessError:
            continue

        commit_rows = [row for row in raw.split('\x1e') if row.strip()]
        repo_index.append({
            'repo_path': str(repo),
            'repo_rel_path': repo_rel_path,
            'agent_id': agent_id,
            'department': department,
            'head_sha': head_sha,
            'commit_count': len(commit_rows),
            'source_type': 'git_commit',
        })

        for row in commit_rows:
            fields = row.strip().split('\x1f')
            if len(fields) < 6:
                continue
            commit_sha, authored_at, committed_at, author_name, author_email, subject = fields[:6]
            body = '\x1f'.join(fields[6:]).strip() if len(fields) > 6 else ''
            stats = parse_numstat(repo, commit_sha)
            date = (committed_at or authored_at)[:10] if (committed_at or authored_at) else None
            commit = {
                'commit_sha': commit_sha,
                'authored_at': authored_at,
                'committed_at': committed_at,
                'timestamp': committed_at or authored_at,
                'date': date,
                'author_name': author_name,
                'author_email': author_email,
                'subject': subject.strip(),
                'body': body,
                'repo_path': str(repo),
                'repo_rel_path': repo_rel_path,
                'agent_id': agent_id,
                'department': department,
                **stats,
            }
            text = build_commit_chunk_text(commit)
            chunk_id = hashlib.sha1(f"{repo}:{commit_sha}".encode()).hexdigest()[:16]
            rec = {
                'chunk_id': chunk_id,
                'agent_id': agent_id,
                'department': department,
                'workspace_path': str(BASE / agent_id) if agent_id in LIVE_AGENTS else str(repo),
                'file_path': f"{repo}/.git:{commit_sha}",
                'source_file_path': f"{repo}/.git",
                'file_type': 'git_commit',
                'date': date,
                'timestamp': commit['timestamp'],
                'title': f"{repo_rel_path} @ {subject.strip() or commit_sha[:12]}",
                'text': text,
                'text_length': len(text),
                'source_type': 'git_commit',
                'repo_path': str(repo),
                'repo_rel_path': repo_rel_path,
                'commit_sha': commit_sha,
                'author_name': author_name,
                'author_email': author_email,
                'commit_subject': subject.strip(),
                'commit_body': body,
                'changed_files': stats['changed_files'],
                'files_changed': stats['files_changed'],
                'insertions': stats['insertions'],
                'deletions': stats['deletions'],
            }
            if not contains_removed_agent_reference(rec):
                records.append(rec)
    return records, repo_index


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = discover_memory_files()
    chunk_records = []
    index = []

    for path in files:
        agent = infer_agent_id(path)
        file_type = file_type_for(path)
        date = path.stem if file_type == 'daily' and path.stem[:4].isdigit() else None
        text = path.read_text(errors='ignore')
        chunks = chunk_markdown(text)
        index.append({
            'agent_id': agent,
            'department': dept_for(agent),
            'file_path': str(path),
            'file_type': file_type,
            'date': date,
            'chunk_count': len(chunks),
            'source_type': 'workspace_markdown',
        })
        for i, chunk in enumerate(chunks, start=1):
            chunk_id = hashlib.sha1(f"{path}:{i}:{chunk['text']}".encode()).hexdigest()[:16]
            rec = {
                'chunk_id': chunk_id,
                'agent_id': agent,
                'department': dept_for(agent),
                'workspace_path': infer_workspace_path(path, agent),
                'file_path': str(path),
                'source_file_path': str(path),
                'file_type': file_type,
                'date': date,
                'heading_path': chunk['heading_path'],
                'title': ' > '.join(chunk['heading_path']) if chunk['heading_path'] else path.name,
                'text': chunk['text'],
                'text_length': len(chunk['text']),
                'source_type': 'workspace_markdown',
            }
            if not contains_removed_agent_reference(rec):
                chunk_records.append(rec)

    git_records, git_index = collect_git_commit_records()
    chunk_records.extend(git_records)
    index.extend(git_index)

    with CHUNKS.open('w') as f:
        for rec in chunk_records:
            f.write(json.dumps(rec) + '\n')

    MANIFEST.write_text(json.dumps({
        'generated_at': datetime.now(UTC).isoformat().replace('+00:00', 'Z'),
        'workspace_root': str(BASE),
        'source_file_count': len(files),
        'git_repo_count': len(git_index),
        'git_commit_chunk_count': len(git_records),
        'chunk_count': len(chunk_records),
        'status': 'discovered_and_chunked',
        'embeddings_built': False,
    }, indent=2))

    INDEX.write_text(json.dumps(index, indent=2))

    print(f'source_files={len(files)}')
    print(f'git_repos={len(git_index)}')
    print(f'git_commit_chunks={len(git_records)}')
    print(f'chunks={len(chunk_records)}')
    print(f'wrote={CHUNKS}')
    print(f'wrote={MANIFEST}')
    print(f'wrote={INDEX}')


if __name__ == '__main__':
    main()
