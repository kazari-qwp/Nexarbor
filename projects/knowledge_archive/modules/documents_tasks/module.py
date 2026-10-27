"""原不可变任务输入、独立交付、修订和真实知识证据回执。"""
from copy import deepcopy
from hashlib import sha256
import hashlib
import json
from pathlib import Path
from uuid import uuid4
from domain.core import CallableTool, Module, access
from domain.json_values import thaw
from ..knowledge_catalog.access import CatalogAccess

TOOLS = json.loads(Path(__file__).with_name("tools.json").read_text(encoding="utf-8"))


class DocumentsTasksModule(Module):
    def __init__(self, directory, config=None, state=None, **access_settings):
        super().__init__("documents.tasks", **access_settings)
        self.directory = Path(directory).resolve()
        self.config, self.state = deepcopy(config or {}), deepcopy(state or {})
        for spec in TOOLS:
            self.tools._add(CallableTool(spec["id"], getattr(self, spec["operation"]), spec["description"], deepcopy(spec["parameters"])))

    def _bind(self, node):
        super()._bind(node)
        source = sha256((node.info.node_id + "\0" + self.module_id).encode()).hexdigest()[:24]
        for tool, spec in zip(self.tools, TOOLS):
            tool.name = "mod_" + sha256((source + "\0" + spec["id"]).encode()).hexdigest()[:24]
            tool.description = node.info.node_id + " · " + spec["name"] + " · " + spec["description"]

    def tasks(self):
        return self.state.setdefault("tasks", {})

    def current_task(self, parameters):
        task = self.tasks().get(parameters.get("task_id", self.state.get("current")))
        if task is None:
            raise ValueError("No current task")
        return task

    def task_reference(self, task):
        return dict(task_id=task["id"], mode=task["mode"], input_id=self.config["input"], result_id=self.config["output"], references=list(task["references"]))

    def task_directory(self, task):
        return self.directory / "workspace/tasks" / task["id"].split("/")[-1]

    async def save_current(self, field, text):
        return (await self._save_current(field, text))[self.config[field]]

    @access()
    async def _save_current(self, node, field, text):
        if node.info.node_id == self.config[field]:
            node.dataer.write(text)
            return True

    @access(channels=["knowledge"])
    async def _fetch_record(self, node, target, record_id, version):
        if node.info.node_id == target:
            return await node.modules.get("knowledge.collection").fetch(id=record_id, version=version)

    async def record(self, id, version):
        descriptor = await CatalogAccess(self).call("locate", dict(id=id))
        return (await self._fetch_record(descriptor["node_id"], id, version))[descriptor["node_id"]]

    async def execute(self, operation, **parameters):
        return next(iter((await self._operate(operation, parameters)).values()))

    async def task_document_read(self, **parameters):
        return await self.execute("task_document_read", **parameters)

    async def task_document_write(self, **parameters):
        return await self.execute("task_document_write", **parameters)

    async def current(self, **parameters):
        return await self.execute("current", **parameters)

    async def begin(self, **parameters):
        return await self.execute("begin", **parameters)

    async def reference(self, **parameters):
        return await self.execute("reference", **parameters)

    async def remember(self, **parameters):
        return await self.execute("remember", **parameters)

    @access(channels=())
    async def _operate(self, node, op, p):
        p = thaw(p)
        if op=='current':return deepcopy(self.tasks().get(self.state.get('current')))
        if op=='begin':
            t=dict(id='task/'+uuid4().hex,mode=p.get('mode','agent'),references=[],receipts=[],revision=0,sources=[])
            self.tasks()[t['id']]=t;self.state['current']=t['id'];home=self.task_directory(t);home.mkdir(parents=True)
            text=p['content'] if isinstance(p['content'],str) else json.dumps(p['content'],ensure_ascii=False)
            (home/'input.md').write_text(text,encoding='utf8');(home/'result.md').write_text('',encoding='utf8')
            await self.save_current('input',text);await self.save_current('output','')
            return self.task_reference(t)
        t=self.current_task(p);home=self.task_directory(t)
        if op=='reference':
            if p.get('intake_id') and p['intake_id'] not in t['references']:t['references'].append(p['intake_id'])
            return self.task_reference(t)
        if op=='remember':
            for r in p['records']:
                key=dict(id=r['id'],version=r['version'])
                if key not in t['receipts']:t['receipts'].append(key)
            return dict(remembered=True)
        if op=='task_document_read':
            target=p.get('node_id',self.config['input']);kind='input' if target==self.config['input'] else 'result' if target==self.config['output'] else None
            if kind is None:raise ValueError('Document is outside task')
            text=(home/(kind+'.md')).read_text('utf8')
            return dict(**self.task_reference(t),node_id=target,content=text,sha256=hashlib.sha256(text.encode()).hexdigest(),**({'immutable':True} if kind=='input' else dict(author=node.info.node_id,revision=t['revision'],sources=deepcopy(t['sources']),receipts=deepcopy(t.get('delivery_receipts',[])))))
        if p.get('expected_revision',t['revision'])!=t['revision']:raise ValueError('Delivery revision changed; read it before retrying')
        for s in p.get('sources',[]):
            if s['node_id'] in (self.config['input'],self.config['output']):continue
            if not s.get('locator') or not s.get('version'):raise ValueError('Knowledge evidence requires record ID and version')
            r=await self.record(s['locator'],s['version'])
            if r['node_id']!=s['node_id']:raise ValueError('Evidence node does not match record')
        for receipt in p.get('receipts',[]):
            key=dict(id=receipt['id'],version=receipt['version'])
            if key not in t['receipts']:raise ValueError('Receipt was not produced by this task')
            r=await self.record(**key)
            if receipt.get('node_id',r['node_id'])!=r['node_id']:raise ValueError('Receipt node does not match record')
        (home/'result.md').write_text(p['content'],encoding='utf8')
        if self.state['current']==t['id']:await self.save_current('output',p['content'])
        t.update(revision=t['revision']+1,sources=p.get('sources',[]),delivery_receipts=p.get('receipts',[]))
        (home/'delivery.json').write_text(json.dumps(t,ensure_ascii=False,indent=2),encoding='utf8')
        return dict(node_id=self.config['output'],revision=t['revision'],written=True,path=str(home/'result.md'))
