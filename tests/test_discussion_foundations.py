"""讨论便笺、席位和同节点成员委派；不替代完整讨论应用验收。"""

import asyncio
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.network_saver import NetworkSaver
from app.runtime.backend import Backend
from app.runtime.requester import as_requester, caller_id, requester_id
from domain.agent import AgentNode
from domain.core import MarkdownNode, Module, Network, Node, NodeInfo
from projects.discussion_collaboration.modules.notes_text import NotesTextModule
from projects.discussion_collaboration.modules.discussion_seat import DiscussionSeatModule
from projects.discussion_collaboration.modules.collab_participant import CollabParticipantModule

ROOT=Path(__file__).resolve().parents[1]


class DiscussionFoundations(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(prefix='.discussion-',dir=ROOT/'build');self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'notes.md';self.path.write_text('',encoding='utf-8')
        self.doc=MarkdownNode(NodeInfo('notes','Notes'),self.path)
        self.actor=AgentNode(NodeInfo('member','Member'))
        self.group=Node(NodeInfo('group','Group'))
        self.saver=NetworkSaver();self.backend=Backend(self.temp.name,network=Network([self.doc,self.actor,self.group]),saver=self.saver)
        self.addCleanup(lambda:self.backend.close())
        self.notes=NotesTextModule(self.transaction,{'title':'Board','separator':' | '});self.doc.install(self.notes)
        self.seat=DiscussionSeatModule({'role':'leader','name':' '});self.actor.install(self.seat)
        self.saver.tables.module_types.update({'notes.text':lambda record:NotesTextModule(self.transaction),'discussion.seat':lambda record:DiscussionSeatModule()})

    def transaction(self,nodes,**options):return self.backend.node_locks.transaction(nodes,**options)

    async def test_note_append_separator_duplicate_and_reused_key(self):
        self.assertEqual((await self.notes.append('one',key='one'))['appended'],3)
        result=await self.notes.append('two',key='two')
        self.assertEqual(result['version'],2);self.assertEqual(result['appended'],6)
        self.assertTrue((await self.notes.append('two',key='two'))['duplicate'])
        with self.assertRaises(ValueError):await self.notes.append('changed',key='two')
        self.assertEqual((await self.notes.read())['content'],'one | two')

    async def test_note_limits_and_partial_file_failure_restore_version_receipts_and_content(self):
        await self.notes.append('one',key='one');self.notes.config['max_chars']=4
        before=deepcopy(self.notes.state)
        with self.assertRaises(ValueError):await self.notes.append('two',key='two')
        self.assertEqual(self.notes.state,before);self.assertEqual(self.doc.dataer.read(),'one')
        self.notes.config['max_chars']=100
        original=self.doc.dataer.write
        def fail(text):original(text);raise OSError('disk fixture failure')
        with patch.object(self.doc.dataer,'write',side_effect=fail):
            with self.assertRaises(OSError):await self.notes.replace('new',key='replace')
        self.assertEqual(self.notes.state,before);self.assertEqual(self.doc.dataer.read(),'one')

    async def test_note_clear_keeps_original_duplicate_receipts(self):
        await self.notes.append('one',key='one');await self.notes.replace('two',key='two')
        result=await self.notes.clear();self.assertEqual(result,{'version':3,'cleared':3})
        duplicate=await self.notes.append('one',key='one')
        self.assertTrue(duplicate['duplicate']);self.assertEqual(duplicate['length'],0)
        self.assertEqual(self.doc.dataer.read(),'')

    async def test_parallel_append_does_not_lose_writes_or_versions(self):
        await asyncio.gather(*(self.notes.append(str(index),key=str(index)) for index in range(12)))
        result=await self.notes.read()
        self.assertEqual(result['version'],12);self.assertEqual(set(result['content'].split(' | ')),{str(index) for index in range(12)})

    async def test_journal_reopen_preserves_note_file_and_bound_tools(self):
        await self.notes.append('durable',key='one');names=[tool.name for tool in self.notes.tools]
        self.backend.save();self.backend.close();self.backend=Backend(self.temp.name,saver=self.saver)
        notes=self.backend.network.get('notes').modules.get('notes.text')
        self.assertEqual((await notes.read())['content'],'durable')
        self.assertEqual([tool.name for tool in notes.tools],names)
        self.assertTrue((await notes.append('durable',key='one'))['duplicate'])

    async def test_seat_name_fallback_role_validation_and_metadata(self):
        self.assertEqual(await self.seat.describe(),{'id':'member','name':'Member','role':'leader'})
        self.seat.config['name']=' Recorder ';self.seat.config['role']='recorder'
        self.assertEqual((await self.seat.describe())['name'],'Recorder')
        before=deepcopy(self.seat.published);self.seat.config['role']='admin'
        with self.assertRaises(ValueError):await self.seat.describe()
        self.assertEqual(self.seat.published,before)

    async def test_seat_cannot_publish_outside_current_transaction(self):
        async with self.transaction(['group']):
            with self.assertRaises(PermissionError):await self.seat.describe()
        self.assertEqual(self.seat.published,{})

    def participant(self):
        calls=[]
        class Integrator(Module):
            def __init__(self):
                super().__init__('integrator.fixture');self.state={'candidate':{'id':'cand-0000000000000000'}}
            async def read(module,include_history=True):
                calls.append(('read',include_history,caller_id.get(),requester_id.get()))
                return {'members':[{'id':'member','branch':'member/dev'}],'candidate':deepcopy(module.state['candidate'])}
            async def submit(module,**arguments):calls.append(('submit',arguments,caller_id.get(),requester_id.get()));return arguments
            async def approve(module,**arguments):calls.append(('approve',arguments,caller_id.get(),requester_id.get()));return arguments
            async def veto(module,**arguments):calls.append(('veto',arguments,caller_id.get(),requester_id.get()));return arguments
        integrator=Integrator()
        participant=CollabParticipantModule({'integrator_module':'integrator.fixture'},modules=[integrator])
        self.group.install(participant)
        return participant,integrator,calls

    async def test_participant_uses_real_requester_and_keeps_immediate_caller(self):
        participant,integrator,calls=self.participant()
        with as_requester('member'):
            result=await participant.submit(commit='abc1234',member='spoofed')
            self.assertEqual(result['member'],'member')
            view=await participant.read()
            self.assertEqual(view['self'],{'id':'member','branch':'member/dev','is_member':True})
            self.assertEqual(calls[0][2:],('group','member'))
            self.assertIsNone(caller_id.get())
        self.assertIsNone(requester_id.get())

    async def test_participant_fills_current_candidate_and_refuses_absent_candidate(self):
        participant,integrator,calls=self.participant()
        with as_requester('member'):
            self.assertEqual((await participant.approve(reason='ok'))['candidate_id'],'cand-0000000000000000')
            self.assertEqual((await participant.veto(candidate_id='explicit',reason='no'))['candidate_id'],'explicit')
            integrator.state['candidate']=None
            with self.assertRaisesRegex(ValueError,'没有待验收'):await participant.approve()
