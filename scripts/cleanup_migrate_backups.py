#!/usr/bin/env python3
"""Preview backup retention; apply only an unchanged, explicitly reviewed plan."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat


def checked_root(raw):
    if not str(raw).strip():
        raise ValueError('Backup root must not be empty')
    path = Path(os.path.abspath(Path(raw).expanduser()))
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Symlink backup root or ancestor refused')
    broad = {Path.home().resolve(), Path(__file__).resolve().parents[1],
             Path('/workspace'), Path('/tmp'), Path('/var'), Path('/home')}
    if path.parent == path or path in broad or len(path.parts) < 3:
        raise ValueError('Broad backup root refused')
    if not path.is_dir():
        raise ValueError('Backup root must be an existing directory')
    return path


def backup_name(name):
    if not re.fullmatch(r'\d{8}-\d{6}', name):
        return False
    try:
        datetime.strptime(name, '%Y%m%d-%H%M%S')
        return True
    except ValueError:
        return False


def fingerprint(path):
    digest = hashlib.sha256()
    count = size = 0
    for item in [path, *sorted(path.rglob('*'))]:
        info = item.lstat()
        if stat.S_ISLNK(info.st_mode) or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise ValueError('Backup contains a symlink or special file')
        record = [item.relative_to(path).as_posix(), info.st_dev, info.st_ino,
                  info.st_mode, info.st_size, info.st_mtime_ns]
        if item.is_file():
            h = hashlib.sha256()
            with item.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    h.update(chunk)
            record.append(h.hexdigest())
            count += 1
            size += info.st_size
        digest.update(json.dumps(record).encode())
    return {'name': path.name, 'sha256': digest.hexdigest(), 'files': count, 'bytes': size}


def make_plan(root, keep):
    if keep < 0:
        raise ValueError('Keep count must not be negative')
    runs = []
    for item in root.iterdir():
        if backup_name(item.name):
            if item.is_symlink():
                raise ValueError('Symlink backup refused')
            if item.is_dir():
                runs.append(item)
    runs.sort()
    info = root.stat()
    return {'version': 1, 'root': str(root), 'root_identity': [info.st_dev, info.st_ino],
            'keep': keep, 'backups': [p.name for p in runs],
            'remove': [fingerprint(p) for p in runs[:max(0, len(runs) - keep)]]}


def apply_plan(root, keep, plan):
    current = make_plan(root, keep)
    if plan != current:
        raise ValueError('Backup plan changed; generate and review a fresh preview')
    if not shutil.rmtree.avoids_symlink_attacks or os.open not in os.supports_dir_fd:
        raise ValueError('Safe directory-relative removal is unavailable on this runtime')
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if [info.st_dev, info.st_ino] != current['root_identity']:
            raise ValueError('Backup root changed during verification')
        for entry in current['remove']:
            if fingerprint(root / entry['name']) != entry:
                raise ValueError('Backup changed during verification')
            shutil.rmtree(entry['name'], dir_fd=descriptor)
    finally:
        os.close(descriptor)
    return current


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('keep', nargs='?', type=int, default=10)
    parser.add_argument('root', nargs='?', default='./1panel-migrate-backups')
    parser.add_argument('--plan', type=Path, help='Write preview here, or read this exact plan with --apply')
    parser.add_argument('--apply', action='store_true', help='Requires user authorization for this exact reviewed plan')
    args = parser.parse_args()
    try:
        root = checked_root(args.root)
        if args.apply:
            if not args.plan:
                raise ValueError('--apply requires a previously reviewed --plan')
            plan = apply_plan(root, args.keep, json.loads(args.plan.read_text(encoding='utf-8')))
        else:
            plan = make_plan(root, args.keep)
            if args.plan:
                target = args.plan.expanduser().resolve()
                if target == root or root in target.parents:
                    raise ValueError('Save the preview outside the backup root')
                with target.open('x', encoding='utf-8') as stream:
                    stream.write(json.dumps(plan, indent=2) + '\n')
        print(json.dumps({'action': 'applied' if args.apply else 'preview', 'plan': plan}, indent=2))
    except (OSError, ValueError) as exc:
        parser.exit(2, f'Cleanup refused: {exc}\n')


if __name__ == '__main__':
    main()
