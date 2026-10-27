"""A bounded adapter to MkDocs; page rendering, navigation and search are upstream."""
import json
from pathlib import Path
import re


class MarkdownWiki:
    def __init__(self,directory):
        self.directory=Path(directory).resolve()

    def publish(self,title,pages):
        from mkdocs.config import load_config
        from mkdocs.commands.build import build
        # Every publication gets its own directory so prior exports remain usable.
        from uuid import uuid4
        output=self.directory/uuid4().hex
        docs=output/'docs';docs.mkdir(parents=True)
        nav=[{'首页':'index.md'}];index=['# '+title,'']
        for page in pages:
            if not re.fullmatch('[a-f0-9]{32}',page['id']):raise ValueError('Invalid wiki page ID')
            name=page.get('title') or page['id']
            file=page['id']+'.md'
            (docs/file).write_text(page['content'],encoding='utf-8')
            nav.append({name:file});index.append('- ['+name.replace('[','').replace(']','')+']('+file+')')
        (docs/'index.md').write_text('\n'.join(index)+'\n',encoding='utf-8')
        configuration=output/'mkdocs.yml'
        configuration.write_text(json.dumps(dict(site_name=title,docs_dir='docs',site_dir='site',nav=nav,plugins=['search'],theme='mkdocs'),ensure_ascii=False,indent=2),encoding='utf-8')
        build(load_config(config_file=str(configuration)))
        return dict(engine='mkdocs',pages=len(pages),configuration=str(configuration),source_directory=str(docs),site_directory=str(output/'site'),index_path=str(output/'site/index.html'))
