"""Compare staged skills, back up changed files, and install approved sources."""
import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(r'C:\Users\zhy\Desktop\UPC')
STAGE = BASE / 'skill-install-20261107'
DEST = Path(r'C:\Users\zhy\.codex\skills')

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    backup = BASE / 'skill-backups' / ('verified-install-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    records = []
    for source in sorted(STAGE.iterdir()):
        if not source.is_dir() or not (source / 'SKILL.md').is_file():
            continue
        if source.name == 'upc-physics':
            rels = [Path(s.strip()) for s in (source / 'release-files.txt').read_text(encoding='utf-8').splitlines() if s.strip() and not s.startswith('#')]
        else:
            rels = [p.relative_to(source) for p in source.rglob('*') if p.is_file()]
        changed = []
        for rel in rels:
            src, dst = source / rel, DEST / source.name / rel
            if not src.is_relative_to(source) or src.is_symlink() or not src.is_file():
                raise RuntimeError(f'Invalid source {src}')
            if not dst.is_file() or digest(src) != digest(dst):
                changed.append(str(rel))
                if args.apply:
                    if dst.exists():
                        saved = backup / source.name / rel
                        saved.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(dst, saved)
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
            if args.apply and digest(src) != digest(dst):
                raise RuntimeError(f'Hash mismatch {dst}')
        records.append({'skill': source.name, 'file_count': len(rels), 'changed_files': changed})
    result = {'applied': args.apply, 'upc_commit': '08f45a8bb6a7b55e58395c2d2d67274faae7c522', 'matt_commit': '4ae2317ddb22b046e26455e4f9c9b3aaaf62212d', 'installed_root': str(DEST), 'backup_if_needed': str(backup), 'skills': records}
    if args.apply:
        (BASE / 'skill-check' / 'verified-install-20261107.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
