"""新 Git 模块 + 实际安装的 Harness 终端 + 临时真实仓库；不调用模型。"""

import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from app.network_saver import NetworkSaver
from app.runtime.backend import Backend
from domain.agent import AgentNode
from domain.core import CallableTool, Link, Network, Node, NodeInfo
from projects.discussion_collaboration.modules.git_integrator import GitIntegratorModule
from projects.discussion_collaboration.modules.git_integrator.state import _GitError, _BusyError, _member_branch

ROOT = Path(__file__).resolve().parents[1]
HARNESS = Path(os.environ.get("DATANET_HARNESS_EXE", str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/DeepSeek Harness/DeepSeek Harness.exe")))
MODULE = "git.integrator.rev_2863bbe53e.rev_c376775a7e"


class OfficialTerminal:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.serial = 0
        self.pending = {}
        self.stderr = bytearray()

    async def start(self):
        env = dict(os.environ, ELECTRON_RUN_AS_NODE="1", TEMP=str(self.directory), TMP=str(self.directory))
        self.process = await asyncio.create_subprocess_exec(
            str(HARNESS), str(ROOT / "adapt/harness/official/official-tools.cjs"),
            cwd=ROOT, env=env, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.reader = asyncio.create_task(self.read())
        self.errors = asyncio.create_task(self.read_errors())
        return await self.request("init", {"directory":str(self.directory), "timeout_seconds":86400})

    async def read_errors(self):
        while data := await self.process.stderr.read(8192):
            self.stderr.extend(data)
            self.stderr[:] = self.stderr[-16000:]

    async def read(self):
        try:
            while line := await self.process.stdout.readline():
                try:message = json.loads(line)
                except ValueError:continue
                future = self.pending.pop(message.get("id"), None)
                if future is not None and not future.done():
                    if "error" in message:future.set_exception(RuntimeError(message["error"]))
                    else:future.set_result(message.get("result"))
        finally:
            for future in self.pending.values():
                if not future.done():future.set_exception(RuntimeError("Official host closed: " + self.stderr.decode("utf-8", "replace")))
            self.pending.clear()

    async def request(self, method, parameters):
        self.serial += 1
        future = asyncio.get_running_loop().create_future()
        self.pending[self.serial] = future
        self.process.stdin.write((json.dumps({"id":self.serial, "method":method, "params":parameters}, ensure_ascii=False) + "\n").encode("utf-8"))
        await self.process.stdin.drain()
        return await asyncio.wait_for(future, 90)

    async def invoke(self, **arguments):
        return await self.request("invoke", {"actor":"group", "name":"pwsh", "arguments":arguments})

    async def close(self):
        if not hasattr(self, "process"):return
        self.process.stdin.close()
        try:await asyncio.wait_for(self.process.wait(), 10)
        except asyncio.TimeoutError:
            self.process.kill()
            await self.process.wait()
        await asyncio.gather(self.reader, self.errors)


@unittest.skipUnless(HARNESS.is_file(), "Requires installed native Harness SDK")
class GitIntegratorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TemporaryDirectory(prefix=".git-integrator-", dir=ROOT / "build")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.repo = self.directory / "repository"
        self.repo.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Migration verification")
        self.git("config", "user.email", "migration@localhost")
        self.base = self.commit("main", "base.txt", "base\n")
        self.one = self.commit("member/one", "one.txt", "one\n", base=self.base)
        self.two = self.commit("member/two", "two.txt", "two\n", base=self.base)
        self.git("checkout", "main")
        self.terminal = OfficialTerminal(self.directory)
        self.addAsyncCleanup(self.terminal.close)
        catalog = await self.terminal.start()
        self.pwsh = next(item for item in catalog if item["name"] == "pwsh")
        self.group = Node(NodeInfo("group", "Group"))
        members = [AgentNode(NodeInfo(member, member)) for member in ("one", "two")]
        for member in members:self.group.links.add(Link(member.info.node_id, "collaboration"))
        self.saver = NetworkSaver()
        self.saver.tables.module_types[MODULE] = lambda record:self.make()
        self.saver.tables.tool_types["pwsh"] = lambda node, record:self.tool()
        self.integrator = self.make()
        self.group.install(self.integrator)
        self.group.install(self.tool())
        self.backend = Backend(self.directory, network=Network([self.group, *members]), saver=self.saver)

    def make(self):
        return GitIntegratorModule({"repository":str(self.repo), "terminal_ref":"pwsh"}, strength=2)

    def tool(self):
        return CallableTool("pwsh", self.terminal.invoke, self.pwsh["description"], self.pwsh["parameters"])

    async def asyncTearDown(self):
        if hasattr(self, "backend"):self.backend.close()

    def git(self, *arguments, check=True):
        result = subprocess.run(["git", *arguments], cwd=self.repo, capture_output=True, text=True,
                                encoding="utf-8", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if check and result.returncode:raise RuntimeError(result.stderr or result.stdout)
        return result.stdout.strip() if check else result

    def commit(self, branch, path, text, base=None):
        if base:self.git("checkout", "-B", branch, base)
        elif self.git("symbolic-ref", "--short", "HEAD") != branch:self.git("checkout", branch)
        (self.repo / path).write_text(text, encoding="utf-8")
        self.git("add", "--", path)
        self.git("commit", "-m", branch + ": " + path)
        return self.git("rev-parse", "HEAD")

    async def candidate(self):
        await self.integrator.submit(member="one", commit=self.one)
        await self.integrator.submit(member="two", commit=self.two)
        return (await self.integrator.integrate())["candidate"]

    async def test_real_merge_candidate_waits_for_all_votes_and_keeps_branch_heads(self):
        candidate = await self.candidate()
        self.assertEqual(candidate["status"], "pending")
        self.assertEqual(self.git("show", candidate["commit"] + ":one.txt"), "one")
        self.assertEqual(self.git("show", candidate["commit"] + ":two.txt"), "two")
        self.assertNotEqual(self.git("rev-parse", "--verify", "refs/heads/nexarbor/integration", check=False).returncode, 0)
        await self.integrator.approve(member="one", candidate_id=candidate["id"])
        self.assertEqual((await self.integrator.read())["candidate"]["status"], "pending")
        passed = (await self.integrator.approve(member="two", candidate_id=candidate["id"]))["candidate"]
        self.assertEqual(passed["status"], "passed")
        self.assertEqual(self.git("rev-parse", "nexarbor/integration"), candidate["commit"])
        self.assertEqual(self.git("rev-parse", "member/one"), self.one)
        self.assertEqual(self.git("rev-parse", "member/two"), self.two)
        self.assertTrue((await self.integrator.approve(member="two", candidate_id=candidate["id"]))["duplicate"])
        logs = list((self.directory / ".nexarbor/command-logs").glob("*.json"))
        self.assertGreater(len(logs), 10)

    async def test_wrong_branch_missing_commit_and_duplicate_submissions(self):
        with self.assertRaisesRegex(_GitError, "不存在"):
            await self.integrator.submit(member="one", commit="f" * 40)
        self.assertEqual(self.integrator.state["last_failure"]["stage"], "validate")
        with self.assertRaisesRegex(_GitError, "不在成员"):
            await self.integrator.submit(member="one", commit=self.two)
        await self.integrator.submit(member="one", commit=self.one)
        self.assertTrue((await self.integrator.submit(member="one", commit=self.one))["duplicate"])
        with self.assertRaisesRegex(_GitError, "已由成员"):
            await self.integrator.submit(member="two", commit=self.one, branch="member/one")
        self.assertIsNone(self.integrator.state["busy"])

    async def test_merge_conflict_keeps_personal_commits_and_records_conflict_details(self):
        self.one = self.commit("member/one", "base.txt", "one change\n", base=self.base)
        self.two = self.commit("member/two", "base.txt", "two change\n", base=self.base)
        self.git("checkout", "main")
        await self.integrator.submit(member="one", commit=self.one)
        await self.integrator.submit(member="two", commit=self.two)
        with self.assertRaisesRegex(_GitError, "冲突"):
            await self.integrator.integrate()
        failure = self.integrator.state["last_failure"]
        self.assertEqual(failure["stage"], "merge")
        self.assertTrue(failure["conflict_lines"])
        self.assertIsNone(self.integrator.state["candidate"])
        self.assertEqual(self.git("rev-parse", "member/one"), self.one)
        self.assertEqual(self.git("rev-parse", "member/two"), self.two)

    async def test_veto_reopen_revotes_and_frozen_acceptance_after_leave(self):
        candidate = await self.candidate()
        await self.integrator.approve(member="one", candidate_id=candidate["id"])
        await self.integrator.veto(member="two", candidate_id=candidate["id"], reason="check")
        with self.assertRaisesRegex(_GitError, "否决"):
            await self.integrator.integrate()
        reopened = (await self.integrator.reopen(candidate_id=candidate["id"], reason="checked"))["candidate"]
        self.assertEqual(reopened["round"], 2)
        self.assertEqual(reopened["votes"], {})
        self.assertEqual(reopened["rounds"][0]["votes"]["two"]["decision"], "veto")
        await self.integrator.approve(member="one")
        await self.integrator.approve(member="two")
        before = deepcopy((await self.integrator.read())["candidate"]["acceptance"])
        await self.integrator.leave(member="two", reason="done")
        after = (await self.integrator.read())["candidate"]
        self.assertEqual(after["acceptance"], before)
        self.assertEqual(after["required_members"], ["one", "two"])

    async def test_external_branch_change_blocks_promotion_and_retry_keeps_votes(self):
        candidate = await self.candidate()
        external = self.commit("external", "external.txt", "external\n", base=self.base)
        self.git("checkout", "main")
        self.git("update-ref", "refs/heads/nexarbor/integration", external)
        await self.integrator.approve(member="one")
        with self.assertRaisesRegex(_GitError, "拒绝覆盖"):
            await self.integrator.approve(member="two")
        state = (await self.integrator.read())["candidate"]
        self.assertEqual(state["status"], "promotion_failed")
        self.assertEqual(self.git("rev-parse", "nexarbor/integration"), external)
        self.git("update-ref", "refs/heads/nexarbor/integration", self.base, external)
        retried = (await self.integrator.promote(candidate_id=candidate["id"]))["candidate"]
        self.assertEqual(retried["status"], "passed")
        self.assertEqual(retried["approved_by"], ["one", "two"])

    async def test_explicit_leave_is_not_restored_by_rediscovery_and_can_complete_acceptance(self):
        candidate = await self.candidate()
        await self.integrator.approve(member="one")
        result = await self.integrator.leave(member="two", reason="exit")
        self.assertEqual(result["candidate"]["status"], "passed")
        view = await self.integrator.read()
        self.assertFalse(next(member for member in view["members"] if member["id"] == "two")["active"])
        self.assertTrue((await self.integrator.leave(member="two"))["duplicate"])
        self.assertEqual(self.git("rev-parse", "nexarbor/integration"), candidate["commit"])

    async def test_busy_operation_rejected_without_overwriting_failure_and_released_after_completion(self):
        entered, release = asyncio.Event(), asyncio.Event()
        original = self.terminal.invoke
        async def hold(**arguments):
            entered.set()
            await release.wait()
            return await original(**arguments)
        next(tool for tool in self.group.tools if tool.name == "pwsh").function = hold
        task = asyncio.create_task(self.integrator.submit(member="one", commit=self.one))
        await entered.wait()
        try:
            with self.assertRaises(_BusyError):await self.integrator.integrate()
            self.assertIsNone(self.integrator.state["last_failure"])
        finally:
            release.set()
            await task
        self.assertIsNone(self.integrator.state["busy"])

    async def test_cold_reopen_preserves_candidate_votes_and_real_tool_factory(self):
        candidate = await self.candidate()
        await self.integrator.approve(member="one")
        self.backend.save()
        self.backend.close()
        self.backend = Backend(self.directory, saver=self.saver)
        self.integrator = self.backend.network.get("group").modules.get(MODULE)
        view = await self.integrator.read()
        self.assertEqual(view["candidate"]["approved_by"], ["one"])
        passed = (await self.integrator.approve(member="two", candidate_id=candidate["id"]))["candidate"]
        self.assertEqual(passed["status"], "passed")
        self.assertEqual(self.git("rev-parse", "nexarbor/integration"), candidate["commit"])

    def test_member_branch_sanitization_is_stable_and_valid(self):
        for value in ("member~1", "中文节点", "../unsafe//id.lock", "a" * 300):
            branch = _member_branch("member/", value)
            self.assertEqual(branch, _member_branch("member/", value))
            self.assertLessEqual(len(branch), 200)
            self.assertEqual(self.git("check-ref-format", "--branch", branch, check=False).returncode, 0)
