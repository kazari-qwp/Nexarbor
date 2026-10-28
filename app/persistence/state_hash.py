"""缓存未变资源的规范 JSON，哈希与原 canonical(document) 完全一致。"""
from hashlib import sha256
from .state_journal import canonical,checksum

class StateHash:
    def __init__(self):self.files={}

    def copy(self):
        other=StateHash();other.files=self.files.copy();return other

    def digest(self, document, changes=None):
        files=document.get('files') if isinstance(document,dict) else None
        if not isinstance(files,dict) or any(not isinstance(key,str) for key in document) or any(not isinstance(key,str) for key in files):
            self.files.clear();return checksum(document)
        changed=set();reset=changes is None
        for operation in changes or ():
            path=operation['path']
            if not path or path==['files']:reset=True
            elif path[0]=='files':changed.add(path[1])
        if reset:self.files.clear()
        for key in self.files.keys()-files.keys():del self.files[key]
        for key,value in files.items():
            if key not in self.files or key in changed:self.files[key]=canonical(value).encode('utf-8')
        digest=sha256();digest.update(b'{')
        for index,key in enumerate(sorted(document)):
            if index:digest.update(b',')
            digest.update(canonical(key).encode('utf-8'));digest.update(b':')
            if key!='files':digest.update(canonical(document[key]).encode('utf-8'));continue
            digest.update(b'{')
            for position,name in enumerate(sorted(files)):
                if position:digest.update(b',')
                digest.update(canonical(name).encode('utf-8'));digest.update(b':');digest.update(self.files[name])
            digest.update(b'}')
        digest.update(b'}');return digest.hexdigest()
