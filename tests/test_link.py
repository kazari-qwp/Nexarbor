"""连接条件、处理函数和节点出边装配的验证。"""

import unittest

from domain.core import DEFAULT_CHANNEL, Link, Links, Multiplier
from domain.core import Node
from domain.core import NodeInfo


class LinkTests(unittest.TestCase):
    def test_default_processor_preserves_strength(self):
        link = Link('target', ('chat', 'tick'))
        self.assertEqual(link.transmit(4, 'chat'), 4)
        self.assertEqual(link.transmit(0, 'tick'), 0)
        self.assertIsNone(link.transmit(4, 'other'))

    def test_single_channel_is_wrapped_as_a_tuple(self):
        link = Link('target', 'chat')
        self.assertEqual(link.channels, ('chat',))
        self.assertEqual(link.transmit(4, 'chat'), 4)
        self.assertIsNone(link.transmit(4))

    def test_omitted_channel_uses_the_shared_default(self):
        link = Link('target')
        self.assertEqual(link.channels, (DEFAULT_CHANNEL,))
        self.assertTrue(link.allows(4))
        self.assertEqual(link.transmit(4), 4)
        self.assertEqual(link.transmit(4, DEFAULT_CHANNEL), 4)
        self.assertIsNone(link.transmit(4, 'other'))

    def test_threshold_is_checked_before_multiplication(self):
        link = Link('target', ('tick',), threshold=5, processor=Multiplier(2))
        self.assertIsNone(link.transmit(4, 'tick'))
        self.assertEqual(link.transmit(5, 'tick'), 10)

    def test_custom_processor_is_only_called_after_conditions_pass(self):
        calls = []

        def process(strength):
            calls.append(strength)
            return strength + 10

        link = Link('target', ('tick',), threshold=2, processor=process)
        self.assertIsNone(link.transmit(3, 'other'))
        self.assertIsNone(link.transmit(1, 'tick'))
        self.assertEqual(calls, [])
        self.assertEqual(link.transmit(3, 'tick'), 13)
        self.assertEqual(calls, [3])

    def test_channels_are_normalized_and_deduplicated(self):
        link = Link('target', ['chat', 'tick', 'chat'])
        self.assertEqual(link.channels, ('chat', 'tick'))
        self.assertFalse(Link('target', ()).allows(1, 'chat'))

    def test_invalid_connection_parameters_are_rejected(self):
        with self.assertRaises(ValueError):
            Link('', ('tick',))
        with self.assertRaises(TypeError):
            Link('target', 123)
        with self.assertRaises(ValueError):
            Link('target', ('',))
        with self.assertRaises(ValueError):
            Link('target', ('tick',), threshold=-1)
        with self.assertRaises(TypeError):
            Link('target', ('tick',), processor=None)

    def test_links_keep_parallel_edges_and_remove_by_identity(self):
        first = Link('target', ('tick',))
        second = Link('target', ('tick',))
        links = Links([first, second, first])
        self.assertEqual(links.list(), [first, second])
        self.assertEqual(len(links), 2)
        self.assertTrue(links.remove(first))
        self.assertEqual(list(links), [second])
        self.assertFalse(links.remove(first))

    def test_node_owns_an_independent_links_collection(self):
        first = Node(NodeInfo('first', '第一个节点'))
        second = Node(NodeInfo('second', '第二个节点'))
        link = Link(second.info.node_id)
        first.links.add(link)
        self.assertEqual(list(first.links), [link])
        self.assertEqual(list(second.links), [])
        self.assertEqual(link.target_id, second.info.node_id)


if __name__ == '__main__':
    unittest.main()
