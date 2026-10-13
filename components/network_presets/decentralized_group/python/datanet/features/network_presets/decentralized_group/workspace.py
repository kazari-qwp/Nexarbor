"""Private Git worktrees and serial integration, scoped to one collaboration group."""
from pathlib import Path
import subprocess


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
        return self.directory / 'workers' / actor.encode().hex()

    def repository(self):
        result = self.git(self.main, 'rev-parse', 'HEAD', check=False) if self.main.exists() else None
        return dict(path=str(self.main), head_commit=result['stdout'].strip() if result and result['exit_code'] == 0 else None)

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
            self.git(self.main, 'worktree', 'add', '-b', 'worker-' + actor.encode().hex(), str(folder).removeprefix('\\\\?\\').replace('\\', '/'), 'main')

    def invoke(self, actor, action, message='Publish contribution'):
        own = self.personal(actor)
        if not own.exists():
            raise ValueError('Start the collaboration before using its workspace')
        if action == 'inspect':
            return dict(personal_path=str(own), integrated_path=str(self.main), branch='worker-' + actor.encode().hex(), status=self.git(own, 'status', '--short')['stdout'])
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
