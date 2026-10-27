"""一次性迁移原讨论协作项目数据，运行时只使用新节点记录。"""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.projects.host_tools import host_tool_name
from projects.discussion_collaboration.runtime import DiscussionModules
from scripts.migrate_town_project import convert_nodes, files_from, read, write_json

CLASSES = {
    "agents.activity":("agents_activity", "AgentsActivityModule"),
    "app.coordinator.entry":("app_coordinator", "AppCoordinatorModule"),
    "collab.board.rev_9191e2380f.rev_96569f0263":("collab_board", "CollabBoardModule"),
    "collab.participant":("collab_participant", "CollabParticipantModule"),
    "discussion.seat":("discussion_seat", "DiscussionSeatModule"),
    "discussion.session.rev_697d80a33d":("discussion_session", "DiscussionSessionModule"),
    "git.integrator.rev_2863bbe53e.rev_c376775a7e":("git_integrator", "GitIntegratorModule"),
    "messages.box":("messages_box", "MessagesBoxModule"),
    "notes.text":("notes_text", "NotesTextModule"),
    "records.store":("records_store", "RecordsStoreModule"),
}


def migrate(source, target, definitions):
    source, target = Path(source).resolve(), Path(target).resolve()
    modules = DiscussionModules(definitions)
    metadata = read(source, "nexarbor.json")
    manifest = read(source, metadata["networks"][metadata["activeNetwork"]]["file"])
    nodes = [read(source, reference["file"]) for reference in manifest["nodes"]]
    for node in nodes:
        if node.get("toolboxes") or node.get("expose"):
            raise ValueError("项目仍含待迁移的旧工具箱/暴露配置：" + node["node_id"])
    resources = files_from(source, manifest)
    for name, content in resources.items():
        path = (target / name).resolve()
        if not path.is_relative_to(target):raise ValueError("项目资源越界")
        if not isinstance(content, str):raise ValueError("讨论项目资源应为原 UTF-8 文本")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_text(encoding="utf-8") != content:
            raise ValueError("拒绝覆盖已修改项目资源：" + name)
        path.write_text(content, encoding="utf-8")
    manifests = {name:read(source, resource["folder"] + "/module.json") for name, resource in metadata["resources"]["modules"].items()}
    records, properties = convert_nodes(nodes, target, modules, manifests)
    modules.host_tools.register(properties)
    for node, record in zip(nodes, records):
        for offer in node.get("offered_tools", []):
            tool = modules.host_tools.make(node["node_id"], offer["ref"])
            record["tables"]["tools"]["members"].append({"tool":tool.name, "description":tool.description, "parameters":tool.parameters, "modules":[]})
        for module in record["tables"]["modules"]:
            if module["module_id"] == "git.integrator.rev_2863bbe53e.rev_c376775a7e":
                reference = module["config"].get("terminal_ref", "harness:pwsh")
                module["config"]["terminal_ref"] = host_tool_name(node["node_id"], reference)
    references = []
    for record in records:
        file = "nodes/" + sha256(record["node_id"].encode()).hexdigest()[:24] + ".json"
        write_json(target / file, record)
        references.append({"file":file})
    runtime = deepcopy(manifest.get("runtime", {}))
    runtime.pop("components", None)
    if runtime.get("templates"):
        raise ValueError("原讨论应用出现待转换的非空模板")
    network = {"format":"nexarbor-project-network/v2", "nodes":references, "files":list(resources),
               "signals":deepcopy(manifest["network"].get("signals", {})), "properties":properties, "runtime":runtime,
               "layout":deepcopy(manifest.get("layout", {})), "view":deepcopy(manifest.get("view", {}))}
    write_json(target / "networks/main.json", network)
    module_resources = {}
    for name, definition in manifests.items():
        if name in ("context.assembler", "tools.collector"):
            module_resources["tool_discovery" if name == "tools.collector" else name] = {"builtin":True}
            continue
        folder, class_name = CLASSES[name]
        updated = deepcopy(definition)
        updated.update(format="nexarbor-module/v4", entry="module.py:" + class_name)
        updated["node_types"] = ["markdown" if item == "text_file" else item for item in updated.get("node_types", [])]
        updated["requires"] = ["tool_discovery" if item == "tools.collector" else item for item in updated.get("requires", [])]
        if name == "git.integrator.rev_2863bbe53e.rev_c376775a7e":
            terminal = updated["config_schema"]["properties"]["terminal_ref"]
            terminal.update(description="本节点真实终端 CallableTool 的名称", default="pwsh")
            terminal.pop("pattern", None)
        write_json(target / "modules" / folder / "module.json", updated)
        module_resources[name] = {"folder":"modules/" + folder}
    write_json(target / "host_tools.json", definitions)
    write_json(target / "nexarbor.json", {"format":"nexarbor-project/v2", "name":metadata["name"], "activeNetwork":"main",
               "networks":{"main":{"name":metadata["name"], "file":"networks/main.json"}},
               "resources":{"modules":module_resources, "host_tools":{"file":"host_tools.json"}}})
    return {"nodes":len(records), "files":len(resources), "offered_tools":sum(len(node.get("offered_tools", [])) for node in nodes)}


if __name__ == "__main__":
    evidence = json.loads((ROOT / "build/official-installations-verification.json").read_text(encoding="utf-8"))
    configured = next(item for item in evidence if item["installation"] == "configured")
    definitions = json.loads((Path(configured["directory"]) / "catalog.json").read_text(encoding="utf-8"))
    result = migrate("E:/DataNet-模块化成品/projects/discussion-collaboration", ROOT / "projects/discussion_collaboration", definitions)
    write_json(ROOT / "build/discussion-project-migration.json", result)
    print(json.dumps(result, ensure_ascii=False))
