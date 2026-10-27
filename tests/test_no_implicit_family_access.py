"""D008：归属关系不授予访问；跨节点调用仍受真实连接/频道/阈值约束。"""
import unittest
from domain.core import Link,Module,Network,Node,NodeInfo,access

class NoImplicitFamilyAccessTests(unittest.TestCase):
    def test_parent_metadata_cannot_bypass_business_connections(self):
        class Callee(Module):
            calls=0
            @access(channels=())
            def identify(self,node):
                self.calls+=1
                return node.info.node_id
        class Caller(Module):
            @access(channels='calls',strength=1)
            def call_child(self,node):
                if node.info.node_id=='sub':return node.modules.get('callee').identify()
                return None
        owner=Node(NodeInfo('owner','owner'));sub=Node(NodeInfo('sub','sub'))
        sub.parent_id='owner'
        network=Network([owner,sub])
        caller,callee=Caller('caller'),Callee('callee')
        owner.install(caller);sub.install(callee)
        self.assertEqual(caller.call_child(),{'owner':None});self.assertEqual(callee.calls,0)
        wrong=Link('sub','other');owner.links.add(wrong)
        self.assertEqual(caller.call_child(),{'owner':None})
        owner.links.remove(wrong);edge=Link('sub','calls',threshold=2);owner.links.add(edge)
        self.assertEqual(caller.call_child(),{'owner':None})
        edge.threshold=1
        self.assertEqual(caller.call_child(),{'owner':None,'sub':{'sub':'sub'}})
        self.assertEqual(callee.calls,1)

if __name__=='__main__':unittest.main()
