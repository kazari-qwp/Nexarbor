"""旧去中心化协作协议在新模块上验证，使用真实工作区、源码快照和磁盘交付。"""

import asyncio
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.network_saver import NetworkSaver
from app.runtime.backend import Backend
from app.runtime.requester import as_requester
from domain.agent import AgentNode
from domain.core import Link, MarkdownNode, Network, Node, NodeInfo
from projects.discussion_collaboration.modules.cooperative_group import CooperativeGroupModule
from projects.discussion_collaboration.modules.cooperative_member import CooperativeMemberModule

ROOT = Path(__file__).resolve().parents[1]


class CooperativeProtocolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="cooperative-", dir=ROOT / "build")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.group = Node(NodeInfo("group", "协作组"))
        self.members = [AgentNode(NodeInfo(name, name)) for name in ("one", "two", "three")]
        self.caller = AgentNode(NodeInfo("caller", "Caller"))
        self.documents = {}
        for name in ("output", "findings"):
            path = self.directory / (name + ".md")
            path.write_text("", encoding="utf-8")
            node = MarkdownNode(NodeInfo(name, name), path)
            self.documents[name] = node
            self.group.links.add(Link(name, "collaboration.delivery"))
        for member in self.members:
            self.group.links.add(Link(member.info.node_id, "collaboration"))
            member.links.add(Link("group", "collaboration"))
            member.install(CooperativeMemberModule(self.execute, strength=2))
        self.group.links.add(Link("caller", "collaboration.result"))
        self.saver = NetworkSaver()
        self.saver.tables.module_types["cooperation.group"] = lambda record: self.make(record.get("state"))
        self.saver.tables.module_types["cooperation.member"] = lambda record: CooperativeMemberModule(self.execute, state=record.get("state"), strength=2)
        self.backend = Backend(self.directory, network=Network([self.group, *self.members, self.caller, *self.documents.values()]), saver=self.saver)
        self.module = self.make()
        self.group.install(self.module)
        self.emitted = []
        self.addCleanup(lambda: self.backend.close())

    def make(self, state=None):
        return CooperativeGroupModule(self.directory, self.transaction, self.emit, self.write_documents,
                                      dict(output="output", findings="findings"), state=state, strength=2)

    def transaction(self, nodes, **options):
        return self.backend.node_locks.transaction(nodes, **options)

    def emit(self, node, **parameters):
        self.emitted.append(parameters)

    def write_documents(self, files):
        self.backend.write_documents(files)

    async def execute(self, actor, prompt):
        raise AssertionError("No model should be invoked by protocol tests")

    async def call(self, actor, operation, **parameters):
        with as_requester(actor):
            return await getattr(self.module, operation)(**parameters)

    async def start(self):
        return await self.call("caller", "start", task="共同实现并验收一个功能")

    async def publish(self, actor="one", text="print(42)\n"):
        info = await self.call(actor, "workspace", action="inspect")
        path = Path(info["personal_path"])
        (path / "test_result.py").write_text(text, encoding="utf-8")
        result = path / "result.txt"
        result.write_text("Ran 1 test: OK", encoding="utf-8")
        published = await self.call(actor, "workspace", action="publish", message="Implement feature and tests")
        self.assertEqual(published["status"], "integrated")
        return info, result

    async def propose(self):
        await self.start()
        info, result = await self.publish()
        candidate = await self.call("one", "finish", action="propose", content="最终成果", evidence="测试通过", test_scripts=["test_result.py"], test_results=[str(result)])
        return candidate, info

    async def test_claims_must_finish_before_proposal_and_publish_afterwards(self):
        await self.start()
        claim = await self.call("one", "claim", action="claim", scope="实现", paths=["src"])
        with self.assertRaisesRegex(ValueError, "未结束"):
            await self.call("two", "finish", action="propose", content="太早", evidence="说明")
        await self.call("one", "claim", action="complete", claim_id=claim["id"], evidence="已验证")
        candidate = await self.call("two", "finish", action="propose", content="成果", evidence="检查通过")
        self.assertEqual(candidate["phase"], "review")
        self.assertEqual(candidate["candidate"]["approvals"], {"two": "检查通过"})
        self.assertEqual(self.documents["output"].dataer.read(), "")

    async def test_review_has_frozen_source_script_result_and_commit(self):
        candidate, info = await self.propose()
        review = candidate["candidate"]["review"]
        manifest = json.loads(Path(review["manifest_path"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest["commit"], review["commit"])
        self.assertEqual(Path(review["test_scripts"][0]).read_text(encoding="utf-8"), "print(42)\n")
        self.assertEqual(Path(review["test_results"][0]).read_text(encoding="utf-8"), "Ran 1 test: OK")
        Path(info["personal_path"], "test_result.py").write_text("changed", encoding="utf-8")
        self.assertEqual(Path(review["test_scripts"][0]).read_text(encoding="utf-8"), "print(42)\n")
        with self.assertRaisesRegex(ValueError, "运行阶段"):
            await self.call("two", "workspace", action="publish")

    async def test_all_approvals_deliver_once_and_notify_caller(self):
        candidate, _ = await self.propose()
        candidate_id = candidate["candidate"]["id"]
        partial = await self.call("two", "finish", action="approve", candidate_id=candidate_id, evidence="复测通过")
        self.assertEqual(partial["phase"], "review")
        self.assertEqual(self.documents["output"].dataer.read(), "")
        final = await self.call("three", "finish", action="approve", candidate_id=candidate_id, evidence="认可")
        self.assertEqual(final["phase"], "completed")
        self.assertEqual(self.documents["output"].dataer.read(), "最终成果")
        archive = self.directory / self.module.state["archive_path"]
        self.assertEqual((archive / "output.md").read_text(encoding="utf-8"), "最终成果")
        self.assertEqual(json.loads((archive / "run.json").read_text(encoding="utf-8"))["phase"], "completed")
        self.assertTrue(self.caller.inputs.pending())

    async def test_reject_returns_to_work_and_stale_approval_cannot_publish(self):
        candidate, _ = await self.propose()
        old = candidate["candidate"]["id"]
        rejected = await self.call("two", "finish", action="reject", candidate_id=old, evidence="缺少边界测试")
        self.assertEqual(rejected["phase"], "running")
        self.assertIsNone(rejected["candidate"])
        self.assertEqual(self.documents["output"].dataer.read(), "")
        self.assertEqual(self.module.state["runs"], {})
        with self.assertRaisesRegex(ValueError, "候选已变化"):
            await self.call("three", "finish", action="approve", candidate_id=old, evidence="旧票")
        revised = await self.call("three", "finish", action="propose", content="修订成果", evidence="补测通过")
        self.assertNotEqual(revised["candidate"]["id"], old)
        self.assertEqual(set(revised["candidate"]["approvals"]), {"three"})
        self.assertIn("缺少边界测试", self.documents["findings"].dataer.read())

    async def test_propose_and_approve_end_turn_reject_does_not(self):
        await self.start()
        first = await self.call("one", "finish_tool", action="propose", content="成果", evidence="验证")
        self.assertEqual(first["format"], "nexarbor-tool-control/v1")
        self.assertTrue(first["conclude"])
        key = first["data"]["candidate"]["id"]
        approved = await self.call("two", "finish_tool", action="approve", candidate_id=key, evidence="通过")
        self.assertTrue(approved["conclude"])
        rejected = await self.call("three", "finish_tool", action="reject", candidate_id=key, evidence="需修复")
        self.assertFalse(rejected["conclude"])

    async def test_exit_releases_claims_and_uses_remaining_members(self):
        candidate, _ = await self.propose()
        key = candidate["candidate"]["id"]
        await self.call("two", "finish", action="approve", candidate_id=key, evidence="通过")
        result = await self.call("three", "member_exit", target="three", reason="无法继续")
        self.assertEqual(result["phase"], "completed")
        self.assertEqual(self.documents["output"].dataer.read(), "最终成果")

    async def test_invalid_script_and_result_paths_do_not_create_candidate(self):
        await self.start()
        await self.publish()
        with self.assertRaisesRegex(ValueError, "测试脚本"):
            await self.call("one", "finish", action="propose", content="成果", evidence="证据", test_scripts=["../outside.py"])
        self.assertIsNone(self.module.state["candidate"])
        outside = self.directory / "outside.txt"
        outside.write_text("external", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "测试结果"):
            await self.call("one", "finish", action="propose", content="成果", evidence="证据", test_results=[str(outside)])
        self.assertIsNone(self.module.state["candidate"])

    async def test_failed_final_document_write_rolls_back_last_vote(self):
        candidate, _ = await self.propose()
        key = candidate["candidate"]["id"]
        await self.call("two", "finish", action="approve", candidate_id=key, evidence="通过")
        before = deepcopy(self.module.state)
        with patch.object(self.documents["output"].dataer, "write", side_effect=OSError("disk failure")):
            with self.assertRaisesRegex(OSError, "disk failure"):
                await self.call("three", "finish", action="approve", candidate_id=key, evidence="通过")
        self.assertEqual(self.module.state, before)
        self.assertEqual(self.documents["output"].dataer.read(), "")

    async def test_reopen_preserves_candidate_materials_and_does_not_replay(self):
        candidate, _ = await self.propose()
        key = candidate["candidate"]["id"]
        self.backend.save()
        self.backend.close()
        self.backend = Backend(self.directory, saver=self.saver)
        self.module = self.backend.network.get("group").modules.get("cooperation.group")
        self.assertEqual(self.module.state["candidate"]["id"], key)
        self.assertEqual(self.module.state["phase"], "review")
        self.assertEqual(len(self.emitted), 1)
        self.assertTrue(Path(self.module.state["candidate"]["review"]["manifest_path"]).is_file())


if __name__ == "__main__":
    unittest.main()
