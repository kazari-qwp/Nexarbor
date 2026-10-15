"""Original-text navigation using CommonMark token line maps; no model or I/O."""
from bisect import bisect_right
from markdown_it import MarkdownIt


class DocumentStructure:
    def __init__(self,text,title=''):
        if not isinstance(text,str):raise TypeError('Document navigation requires text')
        self.text=text
        self.lines=text.splitlines(keepends=True) or ['']
        self.starts=[0]
        for line in self.lines:self.starts.append(self.starts[-1]+len(line))
        # Hide YAML front matter from the parser without shifting original lines.
        parse_lines=list(self.lines)
        if parse_lines[0].strip()=='---':
            closing=next((i for i in range(1,len(parse_lines)) if parse_lines[i].strip() in ('---','...')),None)
            if closing is not None:
                for i in range(closing+1):parse_lines[i]='\n'
        tokens=MarkdownIt('commonmark').parse(''.join(parse_lines))
        root=dict(section_id='document',title=title,level=0,start_line=1,end_line=len(self.lines),parent_id=None,children=[],heading_path=[])
        self.sections=[root];stack=[root]
        for i,token in enumerate(tokens):
            if token.type!='heading_open' or token.map is None or token.level!=0:continue
            level=int(token.tag[1:]);line=token.map[0]+1
            while stack[-1]['level']>=level:stack.pop()
            heading=tokens[i+1].content
            parent=stack[-1]
            section=dict(section_id='L'+str(line),title=heading,level=level,start_line=line,end_line=len(self.lines),parent_id=parent['section_id'],children=[],heading_path=[*parent['heading_path'],heading])
            parent['children'].append(section['section_id']);self.sections.append(section);stack.append(section)
        if not root['title']:root['title']=self.sections[1]['title'] if len(self.sections)>1 else 'Document'
        for i,section in enumerate(self.sections):
            following=self.sections[i+1:]
            section['intro_end_line']=following[0]['start_line']-1 if following else len(self.lines)
            for next_section in following:
                if next_section['level']<=section['level']:
                    section['end_line']=next_section['start_line']-1;break
        self.by_id={s['section_id']:s for s in self.sections}

    def section(self,id):
        if id not in self.by_id:raise ValueError('Unknown section_id; read the outline for this record version')
        return self.by_id[id]

    @staticmethod
    def describe(section):
        return {key:section[key] for key in ['section_id','title','level','parent_id','start_line','end_line','heading_path']}

    def at(self,character):
        line=self.line_at(character)
        return next(s for s in reversed(self.sections) if s['start_line']<=line<=s['end_line'])

    def line_at(self,character):
        if not 0<=character<=len(self.text):raise ValueError('Character position is outside the document')
        return min(len(self.lines),bisect_right(self.starts,character))

    def location(self,start,end):
        return dict(start_char=start,end_char=end,start_line=self.line_at(start),end_line=self.line_at(max(start,end-1)))

    def locate(self,quote,start=None,end=None):
        if isinstance(start,int) and isinstance(end,int) and 0<=start<end<=len(self.text) and self.text[start:end]==quote:
            return self.location(start,end)
        first=self.text.find(quote) if quote else -1
        if first>=0 and self.text.find(quote,first+1)<0:return self.location(first,first+len(quote))
        return None

    def outline(self,offset=0,limit=40):
        if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=100:raise ValueError('Outline offset must be nonnegative and limit 1..100')
        values=[self.describe(s) for s in self.sections[offset:offset+limit]]
        return dict(outline=values,has_structure=len(self.sections)>1,total_sections=len(self.sections),next_offset=offset+limit if offset+limit<len(self.sections) else None)

    def _slice(self,first,last,offset,budget):
        begin=self.starts[first-1];end=self.starts[last]
        if offset>end-begin:raise ValueError('Offset is beyond this context')
        start=begin+offset;stop=min(end,start+budget)
        return dict(content=self.text[start:stop],location=self.location(start,stop),truncated=stop<end,next_offset=offset+stop-start if stop<end else None)

    def context(self,*,view,section_id=None,start_line=None,end_line=None,offset=0,max_chars=6000):
        if type(max_chars) is not int or not 1<=max_chars<=32000 or type(offset) is not int or offset<0:raise ValueError('max_chars must be 1..32000 and offset nonnegative')
        if view=='section':
            selected=self.section(section_id or 'document');first,last=selected['start_line'],selected['end_line']
        elif view=='window':
            if type(start_line) is not int or not 1<=start_line<=len(self.lines):raise ValueError('start_line is outside the document')
            if end_line is not None and (type(end_line) is not int or end_line<start_line):raise ValueError('end_line must not precede start_line')
            first=start_line;last=min(end_line if end_line is not None else first+20,len(self.lines))
            selected=self.at(self.starts[first-1])
        else:raise ValueError('Context view must be section or window')
        ancestors=[];parent=selected
        if view=='section' or first==parent['start_line']:parent=self.by_id.get(parent['parent_id'])
        while parent:
            ancestors.append(parent);parent=self.by_id.get(parent['parent_id'])
        ancestors.reverse();intro_budget=min(max_chars//3,1500);intros=[]
        for ancestor in ancestors:
            end=ancestor['intro_end_line']
            if end<ancestor['start_line'] or intro_budget<=0:continue
            # The original parent introduction carries conditions absent from a child.
            if ancestor['start_line']>=first and end<=last:continue
            excerpt=self._slice(ancestor['start_line'],end,0,min(500,intro_budget))
            intro_budget-=len(excerpt['content'])
            if excerpt['content']:intros.append(dict(section=self.describe(ancestor),**excerpt))
        body=self._slice(first,last,offset,max_chars-sum(len(x['content']) for x in intros))
        siblings=self.by_id[selected['parent_id']]['children'] if selected['parent_id'] else ['document']
        position=siblings.index(selected['section_id'])
        return dict(**body,section=self.describe(selected),ancestor_context=intros,
                    children=[self.describe(self.by_id[x]) for x in selected['children'][:40]],
                    children_truncated=len(selected['children'])>40,
                    previous=self.describe(self.by_id[siblings[position-1]]) if position else None,
                    next=self.describe(self.by_id[siblings[position+1]]) if position+1<len(siblings) else None)
