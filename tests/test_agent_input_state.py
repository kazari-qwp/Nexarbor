"""原 AgentInputs 状态规则及新 Agent/上下文组装器组合；不代替 DSH 恢复验收。"""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from domain.core import MarkdownNode, NodeInfo
from modules.agent import AgentModule
from modules.agent.inputs import AgentInputs
from modules.context_assembler import ContextAssemblerModule


class AgentInputStateTests(unittest.TestCase):
    def test_partial_updates_source_isolation_and_clear(self):
        value = AgentInputs()
        value.update('persona', dict(system_prompt='fixed', tail=['A']))
        value.update('clock', dict(tail=['now']))
        value.update('persona', dict(context=[dict(id='doc', text='facts')]))
        self.assertEqual(value.snapshot()['persona']['system_prompt'], 'fixed')
        value.update('persona', dict(system_prompt='', tail=[]))
        self.assertEqual(value.tail(), ['now'])
        self.assertEqual(value.snapshot()['persona']['context'][0]['text'], 'facts')
        before = value.snapshot()
        with self.assertRaises(ValueError):
            value.update('persona', dict(system_prompt='must rollback', context=[dict(id='x', text=2)]))
        self.assertEqual(value.snapshot(), before)

    def test_all_four_surfaces_accept_actual_document_files(self):
        with TemporaryDirectory(prefix='.agent-inputs-', dir=Path(__file__).resolve().parents[1]) as folder:
            path = Path(folder) / 'source.md'
            path.write_text('实际文档正文', encoding='utf-8')
            ref = dict(file=str(path))
            value = AgentInputs()
            value.update('files', dict(system_prompt=ref, context=[dict(id='guide', text=ref)],
                                       inputs=[dict(id='job', text=ref)], tail=[ref]))
            snap = value.snapshot()['files']
            self.assertEqual(snap['system_prompt'], '实际文档正文')
            self.assertEqual(snap['context'][0]['text'], '实际文档正文')
            self.assertEqual(snap['inputs'][0]['text'], '实际文档正文')
            self.assertEqual(snap['tail'], ['实际文档正文'])

    def test_event_identity_and_state_restore_preserve_acknowledgement(self):
        value = AgentInputs()
        value.update('producer', dict(inputs=[dict(id='event', text='task')], system_prompt='persona'))
        value.acknowledge('producer', 'event')
        value.update('producer', dict(inputs=[dict(id='event', text='task')]))
        self.assertEqual(value.pending(), [])
        with self.assertRaisesRegex(ValueError, 'event ID'):
            value.update('producer', dict(inputs=[dict(id='event', text='different task')]))
        value.update('producer', dict(inputs=[dict(id='event2', text='task')]))
        restored = AgentInputs(value.snapshot())
        self.assertEqual(restored.snapshot(), value.snapshot())
        self.assertEqual(len(restored.pending()), 1)
        self.assertEqual(restored.pending()[0][1]['id'], 'event2')
        restored.acknowledge('producer', 'event2')
        self.assertEqual(len(value.pending()), 1)


class ContextInputIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_preview_and_assembly_only_apply_when_the_agent_is_updated(self):
        with TemporaryDirectory(prefix='.context-inputs-', dir=Path(__file__).resolve().parents[1]) as folder:
            file = Path(folder) / 'memory.md'
            file.write_text('私人记忆', encoding='utf-8')
            node = MarkdownNode(NodeInfo('actor', 'actor'), file)
            agent = AgentModule()
            assembly = ContextAssemblerModule({'sources': [
                {'id': 'event', 'kind': 'inputs', 'type': 'text', 'text': 'one task', 'event_id': 'one'},
                {'id': 'persona', 'kind': 'system_prompt', 'type': 'text', 'text': 'persona'},
            ]})
            node.install(agent)
            node.install(assembly)
            packet = await assembly.preview()
            self.assertEqual(agent.inputs.snapshot(), {})
            self.assertEqual((await assembly.assemble()), packet)
            source = 'prepare:actor:context.assembler:assemble'
            agent.update_inputs(source, **packet['patch'])
            agent.update_inputs(source, **packet['patch'])
            self.assertEqual(len(agent.inputs.pending()), 1)
            agent.inputs.acknowledge(source, 'node:actor:source:event/one')
            agent.update_inputs(source, **(await assembly.assemble())['patch'])
            self.assertEqual(agent.inputs.pending(), [])
            assembly.config['sources'][0]['text'] = 'changed task'
            with self.assertRaisesRegex(ValueError, 'event ID'):
                agent.update_inputs(source, **(await assembly.assemble())['patch'])
            self.assertEqual(node.dataer.read(), '私人记忆')


if __name__ == '__main__':
    unittest.main()
