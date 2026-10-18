"""空错误说明也必须保持失败，不能在JSON-RPC中变成undefined成功。"""
import importlib.util,io,json,unittest
from pathlib import Path
from types import SimpleNamespace

class TransportErrors(unittest.TestCase):
    def test_empty_exception_keeps_an_explicit_failure_type(self):
        file=Path(__file__).resolve().parents[1]/'adapters/harness/backend/transport.py'
        spec=importlib.util.spec_from_file_location('transport_error_test',file);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        stream=io.StringIO();transport=module.Transport(SimpleNamespace(),output=stream)
        def fail(*args):raise PermissionError()
        transport.dispatch=fail
        try:
            transport.answer({'id':17,'method':'denied'})
            self.assertEqual(json.loads(stream.getvalue()),{'id':17,'error':'PermissionError'})
        finally:transport.workers.shutdown()
