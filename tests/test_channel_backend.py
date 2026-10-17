"""Channel-only RPC and persistence with no extension components enabled."""
import tempfile
import unittest
from pathlib import Path
from datanet.core.backend import Backend
from datanet.core.text_node import TextFileNode


class ChannelBackendTests(unittest.TestCase):
    def test_rpc_uses_declared_tool_channels_and_restore_keeps_access(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Backend(folder)
            try:
                text=TextFileNode('notes','Notes','text',app.directory/'notes.md',tool_channels={'read':['notes'],'write':['notes']})
                text.write('content','stored');text.expose=['read']
                app.network.add_node(text);app.root.connect('notes',channels=['notes'])
                query={'actor':'root','target':'notes','strength':1}
                self.assertFalse(app.dispatch('check_access',query)['allowed'])
                self.assertTrue(app.dispatch('check_access',{**query,'channels':['notes']})['allowed'])
                self.assertEqual(app.dispatch('network_structure',{'actor':'root'})['interfaces'],'root')
                request={'actor':'root','target':'notes','tool':'read','arguments':{'request':{'method':'key','key':'content'}},'strength':1}
                self.assertEqual(app.dispatch('invoke_tool',request).items,[{'content':'stored'}])
                self.assertEqual(app.dispatch('invoke_tool',{**request,'tool':'write','arguments':{'key':'content','value':'denied'}}).status,'forbidden')
                for method in ['read','write']:
                    with self.assertRaisesRegex(ValueError,'unknown method'):app.dispatch(method,query)
                app.dispatch('save',{})
            finally:app.close()
            restored=Backend(folder)
            try:
                self.assertEqual(restored.dispatch('invoke_tool',request).items,[{'content':'stored'}])
                self.assertEqual(restored.network.nodes['notes'].tool_channels['write'],['notes'])
            finally:restored.close()
