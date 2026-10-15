"""Resolve reading entries, reusing upstream page metadata and CommonMark tokens."""
import re
from urllib.parse import unquote, urlsplit
from markdown_it import MarkdownIt
from .upstream import page


def identity(record):
    parsed=page(record)
    title=parsed['title']
    if title==record['key']:
        tokens=MarkdownIt('commonmark').parse(parsed['content'])
        title=next((tokens[i+1].content for i,t in enumerate(tokens) if t.type=='heading_open' and t.level==0),title)
    names=[record['id'],record['key'],title,*parsed['aliases']]
    normalized=[]
    for name in names:
        if not name:continue
        folded=name.casefold();normalized.append(folded)
        if folded.endswith('.md'):normalized.append(folded[:-3])
    return title,list(dict.fromkeys(normalized))


def references(record):
    content=page(record)['content'];result=[]
    for token in MarkdownIt('commonmark').parse(content):
        if token.type!='inline':continue
        visible=''.join(t.content if t.type=='text' else '\0' for t in token.children or [])
        for match in re.finditer(r'\[\[([^\]\n\0]+)\]\]',visible):
            target,_,label=match[1].partition('|')
            result.append((target.strip(),label.strip() or target.strip()))
        for child in token.children or []:
            if child.type=='link_open':
                href=child.attrGet('href') or ''
                if not urlsplit(href).scheme and not href.startswith('//'):
                    result.append((unquote(href),unquote(href)))
    return list(dict.fromkeys(result))


def target_parts(target):
    target,_,anchor=target.partition('#')
    if target.lower().endswith('.md'):target=target[:-3]
    return target,anchor
