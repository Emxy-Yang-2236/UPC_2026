"""Prepare an additive, byte-preserving UPC snapshot for reviewed publication."""
import hashlib
import json
import os
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CHECKOUT = ROOT / 'UPC_2026'
SKIP = {'.git', '__pycache__', '.pytest_cache', '.venv', 'venv', '_sync', CHECKOUT.name, 'UPC-repository-sync-20261107'}
SECRET = re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')

def main():
    if not (CHECKOUT / '.git').is_dir():
        raise RuntimeError('Expected sync checkout is missing')
    selected, exclusions = [], []
    for base, dirs, names in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for name in sorted(names):
            p = Path(base)/name
            rel = p.relative_to(ROOT)
            if p.is_symlink():
                raise RuntimeError(f'Review symbolic link before uploading: {rel}')
            if name in {'.env', '.git', '.DS_Store'} or name.startswith('.env.') or p.suffix.lower() in {'.pem','.key'}:
                if name in {'.git', '.DS_Store'}:
                    exclusions.append(rel.as_posix())
                    continue
                raise RuntimeError(f'Review potential credential file: {rel}')
            data = p.read_bytes()
            if SECRET.search(data):
                raise RuntimeError(f'Review potential credential content: {rel}')
            if len(data) >= 95_000_000:
                raise RuntimeError(f'File requires large-data handling: {rel}')
            sha = hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
            selected.append({'path':'UPC/'+rel.as_posix(),'size':len(data),'sha256':hashlib.sha256(data).hexdigest(),'blob':sha})
    for item in selected:
        src=ROOT/Path(item['path']).relative_to('UPC')
        dst=CHECKOUT/item['path']
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,dst)
        if hashlib.sha256(dst.read_bytes()).hexdigest()!=item['sha256']:
            raise RuntimeError(f'Copy verification failed: {item["path"]}')
    state=ROOT/'_sync'
    state.mkdir(exist_ok=True)
    manifest={'repository':'Emxy-Yang-2236/UPC_2026','branch':'zhaohaoyang','mode':'additive; deletions require review','excluded_directories':sorted(SKIP),'excluded_files':exclusions,'files':sorted(selected,key=lambda x:x['path'])}
    (state/'upload-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'files':len(selected),'bytes':sum(x['size'] for x in selected),'manifest':str(state/'upload-manifest.json')},ensure_ascii=True))

if __name__=='__main__':
    main()
