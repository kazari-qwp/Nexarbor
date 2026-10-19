"""The communication layer runs without a graph, component loader or provider."""
import io,json,queue,threading,unittest
from datanet.communication.jsonrpc import JsonRpcTransport

class Lines:
    def __init__(self):self.queue=queue.Queue()
    def __iter__(self):return self
    def __next__(self):
        item=self.queue.get(timeout=5)
        if item is None:raise StopIteration
        return json.dumps(item)+'\n'

class Output:
    def __init__(self):self.queue=queue.Queue()
    def write(self,text):self.queue.put(json.loads(text))
    def flush(self):pass

class JsonRpcTests(unittest.TestCase):
    def test_reverse_callback_can_complete_while_another_request_waits(self):
        lines,out=Lines(),Output();transport=JsonRpcTransport(output=out)
        transport.handler=lambda method,p:transport.host('callback',p) if method=='slow' else p
        thread=threading.Thread(target=transport.run,args=(lines,));thread.start()
        try:
            lines.queue.put({'id':1,'method':'slow','params':{'text':'中文'}})
            callback=out.queue.get(timeout=3);self.assertEqual(callback['method'],'callback')
            lines.queue.put({'id':2,'method':'fast','params':{'alive':True}})
            self.assertEqual(out.queue.get(timeout=3),{'id':2,'result':{'alive':True}})
            lines.queue.put({'host_id':callback['host_id'],'result':'回答'})
            self.assertEqual(out.queue.get(timeout=3),{'id':1,'result':'回答'})
        finally:lines.queue.put(None);thread.join(3)
        self.assertFalse(thread.is_alive());self.assertEqual(transport.pending,{})

    def test_eof_releases_waiter_and_rejects_late_callbacks(self):
        lines,out=Lines(),Output();transport=JsonRpcTransport(output=out)
        transport.handler=lambda method,p:transport.host('waiting',p)
        thread=threading.Thread(target=transport.run,args=(lines,));thread.start()
        lines.queue.put({'id':1,'method':'request'});out.queue.get(timeout=3);lines.queue.put(None)
        response=out.queue.get(timeout=3);thread.join(3)
        self.assertEqual(response['error'],'Host connection closed');self.assertFalse(thread.is_alive());self.assertEqual(transport.pending,{})
        with self.assertRaisesRegex(RuntimeError,'closed'):transport.host('late',{})

    def test_invalid_envelope_and_empty_error_are_explicit(self):
        out=Output();transport=JsonRpcTransport(output=out)
        def fail(method,p):raise PermissionError()
        transport.handler=fail
        transport.run(io.StringIO('[]\n{"id":7,"method":"fail"}\n'))
        self.assertIn('object',out.queue.get(timeout=1)['error']);self.assertEqual(out.queue.get(timeout=1),{'id':7,'error':'PermissionError'})

    def test_timeout_cleans_pending_request(self):
        transport=JsonRpcTransport(output=io.StringIO(),host_timeout=lambda m,p:.001)
        try:
            with self.assertRaises(TimeoutError):transport.host('no-answer',{})
            self.assertEqual(transport.pending,{})
        finally:transport.workers.shutdown()
