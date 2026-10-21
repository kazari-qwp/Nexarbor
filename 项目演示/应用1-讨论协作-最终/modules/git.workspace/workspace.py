"""Private Git worktrees and serial integration, scoped to one collaboration group."""
from pathlib import Path
import subprocess
import json, shutil, tarfile
from hashlib import sha256
from uuid import uuid4


class Workspace:
    def __init__(self, directory, members):
        self.directory = Path(directory)
        self.main = self.directory / 'main'
        self.members = members

    def git(self, cwd, *args, check=True):
        result = subprocess.run(['git', '-c', 'core.longpaths=true', '-C', str(cwd).removeprefix('\\\\?\\'), *args], stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding='utf-8', errors='replace',
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=60)
        if check and result.returncode:
            raise RuntimeError(result.stderr or result.stdout)
        return dict(exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)

    def personal(self, actor):
        if actor not in self.members:
            raise PermissionError('Workspace belongs to another group')
        return self.directory / 'workers' / sha256(actor.encode()).hexdigest()[:16]

    def repository(self):
        result = self.git(self.main, 'rev-parse', 'HEAD', check=False) if self.main.exists() else None
        return dict(path=str(self.main), head_commit=result['stdout'].strip() if result and result['exit_code'] == 0 else None)

    def proposal(self, actor, scripts, results, logs, artifacts):
        commit = self.repository()['head_commit']
        id = str(uuid4())
        directory = self.directory / 'reviews' / id
        directory.mkdir(parents=True)
        archive = directory / 'source.tar'
        source = directory / 'source'
        source.mkdir()
        if self.git(self.main, 'ls-tree', '-r', '--name-only', commit)['stdout']:
            self.git(self.main, 'archive', '--format=tar', '--output', str(archive).removeprefix('\\\\?\\'), commit)
            with tarfile.open(archive, mode='r:') as tar:
                tar.extractall(source, filter='data')
        script_files = []
        for relative in scripts:
            file = (source / relative).resolve()
            if not file.is_relative_to(source.resolve()) or not file.is_file():
                raise ValueError('测试脚本须是当前提交中的工作区相对文件路径')
            script_files.append(str(file))
        result_files = []
        for i, value in enumerate(results):
            file = Path(value) if Path(value).is_absolute() else self.personal(actor) / value
            file = file.resolve()
            if not any(file.is_relative_to(Path(root).resolve()) for root in (self.personal(actor), artifacts, self.main)) or not file.is_file():
                raise ValueError('测试结果须位于自己的工作目录、运行产物目录或共同目录')
            target = directory / 'results' / (str(i) + '_' + file.name)
            target.parent.mkdir(exist_ok=True)
            shutil.copy2(file, target)
            result_files.append(str(target))
        terminal = []
        for record in logs:
            file = Path(record['path'])
            target = directory / 'logs' / file.name
            target.parent.mkdir(exist_ok=True)
            shutil.copy2(file, target)
            terminal.append({**record, 'path': str(target)})
        manifest = directory / 'manifest.json'
        manifest.write_text(json.dumps(dict(commit=commit, proposer=actor, test_scripts=script_files, test_results=result_files, execution_logs=terminal), ensure_ascii=False, indent=2), encoding='utf-8')
        return dict(id=id, commit=commit, source_path=str(source), manifest_path=str(manifest), test_scripts=script_files, test_results=result_files, execution_log_count=len(terminal))

    def prepare(self):
        self.main.mkdir(parents=True, exist_ok=True)
        self.git(self.main, 'init', '-b', 'main')
        self.git(self.main, 'config', 'user.name', 'DataNet')
        self.git(self.main, 'config', 'user.email', 'datanet@localhost')
        self.git(self.main, 'config', 'commit.gpgsign', 'false')
        self.git(self.main, 'config', 'core.longpaths', 'true')
        if self.git(self.main, 'rev-parse', '--verify', 'HEAD', check=False)['exit_code']:
            self.git(self.main, 'commit', '--allow-empty', '-m', 'Initialize shared workspace')
        for actor in self.members:
            folder = self.personal(actor)
            if folder.exists():
                continue
            folder.parent.mkdir(parents=True, exist_ok=True)
            self.git(self.main, 'worktree', 'add', '-b', 'worker-' + sha256(actor.encode()).hexdigest()[:16], str(folder).removeprefix('\\\\?\\').replace('\\', '/'), 'main')

    def invoke(self, actor, action, message='Publish contribution'):
        own = self.personal(actor)
        if not own.exists():
            raise ValueError('Start the collaboration before using its workspace')
        if action == 'inspect':
            return dict(personal_path=str(own), integrated_path=str(self.main), branch='worker-' + sha256(actor.encode()).hexdigest()[:16], status=self.git(own, 'status', '--short')['stdout'])
        if action == 'sync':
            result = self.git(own, 'merge', '--no-edit', 'main', check=False)
            return dict(status='ok' if result['exit_code'] == 0 else 'conflict', **result)
        if action != 'publish':
            raise ValueError('Unknown workspace action')
        self.git(own, 'add', '-A')
        if self.git(own, 'diff', '--cached', '--quiet', check=False)['exit_code']:
            self.git(own, 'commit', '-m', message)
        commit = self.git(own, 'rev-parse', 'HEAD')['stdout'].strip()
        result = self.git(self.main, 'merge', '--no-edit', '--no-ff', commit, check=False)
        if result['exit_code']:
            self.git(self.main, 'merge', '--abort', check=False)
        return dict(status='integrated' if result['exit_code'] == 0 else 'conflict', commit=commit, integrated_path=str(self.main), **result)
