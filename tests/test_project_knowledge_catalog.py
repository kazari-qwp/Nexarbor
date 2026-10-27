"""实际资料库模块的原存储引擎，验证持久化、来源和可恢复物化。"""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from projects.knowledge_archive.modules.knowledge_catalog.store import KnowledgeStore

ROOT = Path(__file__).resolve().parents[1]


class ProjectKnowledgeCatalogTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "build").mkdir(exist_ok=True)
        self.folder = TemporaryDirectory(prefix="catalog-", dir=ROOT / "build")
        self.addCleanup(self.folder.cleanup)
        self.directory = Path(self.folder.name)
        self.store = KnowledgeStore(self.directory / "knowledge", owner_node="catalog")

    def test_four_storage_types_and_owner_survive_reopen(self):
        cases = [("csv", {"name": "001", "n": 2}, {"name": "string", "n": "integer"}),
                 ("sqlite", {"name": "中文", "n": 3}, {"name": "string", "n": "integer"}),
                 ("rag", "长文档：网络节点支持检索和持久化。", {}),
                 ("wiki", "# 知识页面\n稳定标识引用。", {})]
        for kind, value, schema in cases:
            with self.subTest(storage=kind):
                collection = self.store.create_collection(kind, kind, schema=schema)
                self.store.owner_nodes[collection["id"]] = "node-" + kind
                record = self.store.store(collection["id"], value, key="item")
                self.assertEqual(record["content"], value)
                self.assertEqual(record["node_id"], "node-" + kind)
                self.assertEqual(self.store.search(collection=collection["id"])["total"], 1)
                if kind in ("rag", "wiki"):
                    self.assertEqual(record["index"]["reason"], "embedding_not_configured")
        restored = KnowledgeStore(self.store.directory, owner_node="catalog")
        restored.owner_nodes = dict(self.store.owner_nodes)
        self.assertEqual(len(restored.catalog()), 4)
        for collection in restored.catalog():
            hit = restored.search(collection=collection["id"])["items"][0]
            self.assertEqual(restored.fetch(hit["id"])["node_id"], "node-" + collection["storage"])

    def test_fixed_version_evidence_staleness_and_delete_history(self):
        raw = self.store.create_collection("原文", "rag")
        wiki = self.store.create_collection("整理", "wiki")
        source = self.store.store(raw["id"], "初始资料", key="source")
        same = self.store.store(raw["id"], "初始资料", key="source")
        self.assertTrue(same["unchanged"])
        page = self.store.store(wiki["id"], "# 记录\n基于资料的整理", key="page", sources=[source["id"]])
        self.store.update(source["id"], "更新资料", expected_version=1)
        self.assertTrue(self.store.fetch(page["id"])["needs_refresh"])
        self.assertEqual(self.store.fetch(**source["fetch"])["content"], "初始资料")
        self.assertEqual(source["evidence"], {"node_id": "catalog", "locator": source["id"], "version": 1})
        with self.assertRaisesRegex(ValueError, "Version conflict"):
            self.store.update(source["id"], "错误写入", expected_version=1)
        self.store.delete(source["id"], expected_version=2)
        self.assertEqual(self.store.search("更新资料")["total"], 0)
        with self.assertRaises(KeyError):
            self.store.fetch(source["id"])
        self.assertEqual(self.store.fetch(source["id"], 2)["content"], "更新资料")

    def test_partial_typed_intake_sources_and_whole_batch_routing(self):
        for kind in ("csv", "sqlite"):
            with self.subTest(storage=kind):
                schema = {"name": "string", "n": "integer", "enabled": "boolean"}
                target = self.store.create_collection(kind, kind, schema=schema)
                original = self.directory / (kind + ".csv")
                original.write_text("name,n,enabled\n0042,42,true\n", encoding="utf-8")
                values = [{"name": str(i).zfill(4), "n": str(i), "enabled": "true"} for i in range(4)]
                intake = self.store.stage(values, purpose=kind, original_file=original)
                preview = self.store.intake(intake["id"], preview=True, offset=1, limit=2)
                self.assertEqual(preview["total_items"], 4)
                self.assertEqual(preview["content"], values[1:3])
                partial = self.store.commit_intake(intake["id"], target["id"], indices=[0, 2])
                self.assertEqual(partial["remaining_indices"], [1, 3])
                self.assertIsNone(self.store.route(intake["id"])["collection"])
                done = self.store.commit_intake(intake["id"], target["id"])
                self.assertEqual(len(done["records"]), 4)
                self.assertEqual(self.store.commit_intake(intake["id"], target["id"]), done)
                hit = self.store.search(collection=target["id"], filters={"name": "0002"})["items"][0]
                record = self.store.fetch(hit["id"])
                self.assertEqual(record["content"], {"name": "0002", "n": 2, "enabled": True})
                self.assertEqual(Path(record["origins"][0]["archived_path"]).read_bytes(), original.read_bytes())
                complete_intake = self.store.stage(values, purpose=kind)
                self.store.commit_intake(complete_intake["id"], target["id"])
                self.assertEqual(self.store.route(complete_intake["id"])["collection"], target["id"])
                self.assertEqual(self.store.export(target["id"], "csv")["count"], 4)

    def test_interrupted_materialization_recovers_original_content(self):
        target = self.store.create_collection("恢复", "wiki")
        def fail(record_id):
            raise OSError("simulated interruption")
        self.store._materialize = fail
        with self.assertRaisesRegex(OSError, "interruption"):
            self.store.store(target["id"], "# 恢复\n中断前的原文", key="recover")
        restored = KnowledgeStore(self.store.directory, owner_node="catalog")
        hit = restored.search("中断前")["items"][0]
        record = restored.fetch(hit["id"])
        self.assertEqual(record["state"], "ready")
        self.assertEqual(record["content"], "# 恢复\n中断前的原文")

    def test_database_aggregation_excludes_deleted_and_binds_fields(self):
        target = self.store.create_collection("统计", "sqlite", schema={"group": "string", "amount": "integer"})
        records = [self.store.store(target["id"], {"group": "A", "amount": n}, key=str(n)) for n in (2, 3, 5)]
        self.store.delete(records[-1]["id"], expected_version=1)
        query = self.store.query(target["id"], group_by=["group"], aggregate={"function": "sum", "field": "amount"})
        self.assertEqual(query["items"], [{"group": "A", "value": 5}])
        with self.assertRaisesRegex(ValueError, "Unknown database field"):
            self.store.query(target["id"], fields=["amount); DROP TABLE records;--"])
        self.assertEqual(self.store.search(collection=target["id"])["total"], 2)

    def test_short_chinese_search_and_versioned_document_navigation(self):
        target = self.store.create_collection("文档", "rag")
        record = self.store.store(target["id"], "# 总览\n节点和图。\n## 细节\n完整原文。", key="doc")
        self.assertEqual(self.store.search("图")["total"], 1)
        self.assertEqual(self.store.search("节点")["total"], 1)
        outline = self.store.fetch(record["id"], view="outline")
        section = outline["outline"][-1]["read"]
        self.store.update(record["id"], "# 新版\n不同内容。", expected_version=1)
        self.assertIn("完整原文", self.store.fetch(**section)["content"])
        self.assertEqual(self.store.fetch(**section)["version"], 1)
        self.assertEqual(self.store.search(allowed_collections=[])["total"], 0)

    def test_association_requires_exact_content_and_dismiss_keeps_source(self):
        target = self.store.create_collection("原文", "rag")
        record = self.store.store(target["id"], "同一份原文")
        intake = self.store.stage("不同原文")
        with self.assertRaisesRegex(ValueError, "differs"):
            self.store.finish_intake(intake["id"], "associate", record_id=record["id"])
        with self.assertRaises(ValueError):
            self.store.finish_intake(intake["id"], "dismiss")
        self.store.finish_intake(intake["id"], "dismiss", reason="不是本次所需资料")
        self.assertEqual(self.store.intake(intake["id"])["content"], "不同原文")
        same = self.store.stage("同一份原文")
        self.store.finish_intake(same["id"], "associate", record_id=record["id"])
        self.assertEqual(self.store.intake(same["id"])["status"], "completed")


if __name__ == "__main__":
    unittest.main()
