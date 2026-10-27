"""原命令日志的真实文件、截断输出、私有查询和候选证据归档。"""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from projects.discussion_collaboration.modules.cooperative_group.command_logs import CommandLogs
from tests.test_cooperative_protocol import CooperativeProtocolTests
from tests.test_git_integrator import OfficialTerminal
from adapt.harness.executor import NativeExecutor
from app.projects.host_tools import host_tool_name
from projects.discussion_collaboration.runtime import DiscussionProject

ROOT = Path(__file__).resolve().parents[1]


class CommandLogTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="command-logs-", dir=ROOT / "build")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.logs = CommandLogs(self.directory)

    def record(self, actor="one", result=None, command="python -m unittest"):
        self.logs.record(dict(name="pwsh", actor=actor, arguments={"command": command}, result=result or {"content": [{"type": "text", "text": "OK"}], "value": {"stdout": {"text": "OK", "truncated": False}}}))
        return self.logs.logs(actor)[-1]

    def test_full_spill_is_saved_and_secret_redacted(self):
        spill = self.directory / "spill.txt"
        spill.write_text("complete output\napi_key=should-hide", encoding="utf-8")
        row = self.record(command="python script.py --api_key=test-secret", result={"content": [], "value": {"stdout": {"text": "tail", "truncated": True, "spillPath": str(spill)}}})
        saved = json.loads(Path(row["path"]).read_text(encoding="utf-8"))
        self.assertTrue(saved["streams"]["stdout"]["complete"])
        self.assertIn("complete output", saved["streams"]["stdout"]["text"])
        self.assertNotIn("should-hide", json.dumps(saved))
        self.assertNotIn("test-secret", json.dumps(saved))

    def test_only_command_results_are_recorded_and_owner_is_enforced(self):
        self.logs.record(dict(name="read", actor="one", arguments={}, result={}))
        self.assertEqual(self.logs.logs("one"), [])
        row = self.record()
        with self.assertRaisesRegex(ValueError, "不属于"):
            self.logs.logs("two", [row["id"]])
        self.assertEqual(self.logs.tool_datanet_command_logs("one", {"action": "list"})["total"], 1)

    def test_cold_reopen_and_paged_read_keep_original_command(self):
        row = self.record()
        restored = CommandLogs(self.directory)
        self.assertEqual(restored.logs("one")[0]["command"], "python -m unittest")
        first = restored.tool_datanet_command_logs("one", {"action": "read", "log_id": row["id"], "limit": 20})
        rest = restored.tool_datanet_command_logs("one", {"action": "read", "log_id": row["id"], "offset": first["next_offset"], "limit": first["total_chars"]})
        self.assertEqual(first["content"] + rest["content"], Path(row["path"]).read_text(encoding="utf-8"))


class CooperativeLogEvidenceTests(CooperativeProtocolTests):
    async def test_proposal_selects_only_own_logs_and_copies_full_evidence(self):
        await self.start()
        logs = self.module.command_log_store
        logs.record(dict(name="pwsh", actor="one", arguments={"command": "python tests.py"}, result={"content": [{"type": "text", "text": "all checks passed"}]}))
        log = logs.logs("one")[0]
        result = await self.call("one", "finish", action="propose", content="成果", evidence="终端验证", log_ids=[log["id"]])
        manifest = json.loads(Path(result["candidate"]["review"]["manifest_path"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest["execution_logs"][0]["id"], log["id"])
        self.assertEqual(json.loads(Path(manifest["execution_logs"][0]["path"]).read_text(encoding="utf-8"))["arguments"]["command"], "python tests.py")
        self.assertEqual(result["candidate"]["review"]["execution_log_count"], 1)


class NativeCommandLogTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_official_terminal_is_captured_with_real_requester(self):
        with TemporaryDirectory(prefix="native-command-log-", dir=ROOT / "build") as directory:
            project = DiscussionProject(directory)
            terminal = OfficialTerminal(directory)
            try:
                await terminal.start()
                async def official(actor, name, arguments):
                    return await terminal.request("invoke", dict(name=name, arguments=arguments))
                project.official_port = official
                backend = project.backend
                executor = NativeExecutor(backend.network, None, bindings=backend.bindings, states=backend.agents, locks=backend.node_locks)
                await executor.prepare({"actor": "executor-1"})
                result = await executor.invoke({"actor": "executor-1", "name": host_tool_name("collab", "harness:pwsh"), "arguments": {"description": "Verify native command log capture", "command": "Write-Output COOPERATIVE_LOG_NATIVE"}})
                self.assertFalse(result["isError"])
                rows = project.command_logs().logs("executor-1")
                self.assertEqual(len(rows), 1)
                self.assertIn("COOPERATIVE_LOG_NATIVE", Path(rows[0]["path"]).read_text(encoding="utf-8"))
                self.assertEqual(project.command_logs().logs("collab"), [])
            finally:
                await terminal.close()
                project.close()


def load_tests(loader, tests, pattern):
    return unittest.TestSuite([loader.loadTestsFromTestCase(CommandLogTests), loader.loadTestsFromTestCase(NativeCommandLogTests), CooperativeLogEvidenceTests("test_proposal_selects_only_own_logs_and_copies_full_evidence")])
