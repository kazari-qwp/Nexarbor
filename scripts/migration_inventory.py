"""索引原项目文件，保留人工语义审查记录；不会执行原项目源码。"""

from collections import Counter
from pathlib import Path
import ast
import csv
import hashlib
import json
import os
import re
import subprocess

SOURCE = Path('E:/DataNet-模块化成品').resolve()
TARGET = Path(__file__).resolve().parents[1]
OUTPUT = TARGET / 'docs/migration'
EXCLUDED = {'.git', 'node_modules', '.venv', 'build', '__pycache__', '.pytest_cache',
            'dist', '.nexarbor', 'workspace', 'native-logs', 'maker-logs', '.cache'}
SUFFIXES = {'.py', '.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx', '.json', '.yaml',
            '.yml', '.toml', '.md', '.txt', '.cmd', '.ps1', '.html', '.css', '.svg'}


def classify(relative):
    if relative.startswith('frontends/'):
        return 'frontend', relative
    if relative.startswith(('adapters/', 'communication/')):
        return 'adapt', 'adapt/' + relative
    if relative.startswith('shared/'):
        return 'shared', '待审：app/shared 或 frontends/shared'
    if relative.startswith(('projects/', '项目演示/', 'resources/examples/')):
        return 'application-project', 'projects/<应用>/'
    if relative.startswith('python/datanet/core/'):
        return 'legacy-core', '待审：行为迁到 domain/app；旧 Node/AgentNode/ctx 实现最终移除'
    if relative.startswith(('python/', 'executors/')):
        return 'platform-service', 'app/ 或 adapt/'
    if '/skills/' in relative or relative.endswith('SKILL.md'):
        return 'skill-and-prompt', '按平台与应用归属迁移，并重写旧协议说明'
    if relative.startswith('extensions/'):
        return 'component', '待审：仅三个内置模块留 modules，其余业务模块放 projects'
    if relative.startswith('tests/') or '/test/' in relative:
        return 'test', 'tests/：保留原断言，迁移执行入口'
    if relative.startswith('scripts/'):
        return 'script', 'scripts/：逐项确认仍被使用'
    if relative.startswith('configs/'):
        return 'configuration', 'app/config 或 projects/<应用>/'
    if relative.startswith('docs/') or relative.endswith('.md'):
        return 'documentation', 'docs/：更新新核心机制'
    return 'root-or-resource', '待审：保留、迁移或删除需给出理由'


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    tracked = set(filter(None, subprocess.check_output(
        ['git', '-C', str(SOURCE), 'ls-files', '-z']).decode('utf-8').split('\0')))
    paths = set(tracked)
    # 原仓库忽略了部分开发脚本和测试；不能仅因未受 Git 跟踪就遗漏。
    for root, directories, files in os.walk(SOURCE):
        directories[:] = [name for name in directories if name not in EXCLUDED]
        for name in files:
            path = Path(root) / name
            if name.startswith('.env') or path.suffix.lower() not in SUFFIXES:
                continue
            paths.add(path.relative_to(SOURCE).as_posix())
    previous = {}
    csv_path = OUTPUT / 'FILE_INVENTORY.csv'
    if csv_path.exists():
        with csv_path.open(encoding='utf-8-sig', newline='') as stream:
            previous = {row['source_path']: row for row in csv.DictReader(stream)}
    rows = []
    for relative in sorted(paths):
        path = SOURCE / relative
        category, target = classify(relative)
        row = dict(source_path=relative, source_origin='git' if relative in tracked else 'local-source',
                   category=category, proposed_target=target, bytes=0, lines='', sha256='',
                   top_level_symbols='', imports='', review_status='结构已索引；语义待审',
                   decision='', evidence='')
        if not path.is_file() or not path.resolve().is_relative_to(SOURCE):
            row['review_status'] = '缺失或外部链接；需人工核对'
            rows.append(row)
            continue
        content = path.read_bytes()
        row['bytes'] = len(content)
        row['sha256'] = hashlib.sha256(content).hexdigest()
        if b'\0' not in content[:8192]:
            text = content.decode('utf-8-sig', errors='replace')
            row['lines'] = len(text.splitlines())
            if path.suffix == '.py':
                try:
                    tree = ast.parse(text)
                    row['top_level_symbols'] = '; '.join(n.name for n in tree.body
                        if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)))
                    row['imports'] = '; '.join(dict.fromkeys(
                        n.module or '.' for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)))
                except SyntaxError:
                    row['review_status'] = '结构解析失败；语义待审'
            elif path.suffix in ('.js', '.jsx', '.mjs', '.cjs'):
                row['imports'] = '; '.join(dict.fromkeys(re.findall(
                    r"(?:from\s+|require\(\s*|import\(\s*)[\"']([^\"']+)[\"']", text)))
        else:
            row['review_status'] = '二进制/资源；归属待审'
        old = previous.get(relative)
        if old and old.get('sha256') == row['sha256']:
            for key in ('proposed_target', 'review_status', 'decision', 'evidence'):
                row[key] = old.get(key, row[key])
        rows.append(row)
    with csv_path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = dict(source=str(SOURCE), source_commit=subprocess.check_output(
        ['git', '-C', str(SOURCE), 'rev-parse', 'HEAD']).decode().strip(),
        inventory_count=len(rows), local_source_count=len(paths - tracked),
        total_bytes=sum(row['bytes'] for row in rows),
        categories=dict(Counter(row['category'] for row in rows)),
        inventory_note='Git 文件及本地产品源码/测试；排除安装依赖、缓存、构建、凭据。结构索引不等于语义审查完成。')
    (OUTPUT / 'inventory_summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
