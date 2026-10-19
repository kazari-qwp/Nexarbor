"""Import boundary checks for core, wire transports, shared contracts and UI."""
import ast,re,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class LayerBoundaries(unittest.TestCase):
    def test_python_layers_do_not_import_each_other_backwards(self):
        for layer,forbidden in [('core',('datanet.communication','datanet.studio','adapters','frontends')),('communication',('datanet.core','datanet.studio','adapters','frontends'))]:
            for path in (ROOT/'python/datanet'/layer).rglob('*.py'):
                tree=ast.parse(path.read_text(encoding='utf-8'))
                for node in ast.walk(tree):
                    names=[n.name for n in node.names] if isinstance(node,ast.Import) else [node.module or ''] if isinstance(node,ast.ImportFrom) else []
                    for name in names:self.assertFalse(any(name==f or name.startswith(f+'.') for f in forbidden),(path,name))

    def test_browser_and_shared_modules_have_no_host_implementation_dependency(self):
        for folder in ['frontends/network-editor/src','shared','communication']:
            for path in (ROOT/folder).rglob('*'):
                if path.suffix not in ('.js','.jsx','.mjs'):continue
                imports=re.findall(r"(?:from\s+|import\s*\(\s*|import\s+)[\"']([^\"']+)",path.read_text(encoding='utf-8'))
                for name in imports:
                    if name.startswith('.'):
                        target=(path.parent/name.split('?')[0]).resolve();relative=target.relative_to(ROOT).as_posix()
                        if folder.startswith('frontends'):self.assertTrue(relative.startswith(('frontends/network-editor/src/','frontends/network-editor/node_modules/','shared/')) or relative=='communication/editor-client.js',(path,name))
                        else:self.assertTrue(relative.startswith(('communication/','shared/')),(path,name))
                    if folder=='shared' or path.name=='editor-client.js':self.assertFalse(name.startswith('node:'),(path,name))
