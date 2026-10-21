"""Bounded source/result pages; long lines never defeat the output budget."""

def text_page(source,args,*,default_lines=200,max_lines=400):
    line=args.get('start_line',1);count=args.get('line_count',default_lines)
    if type(line) is not int or line<1 or type(count) is not int or not 1<=count<=max_lines:raise ValueError(f'行号从1开始，每次1至{max_lines}行')
    limit=args.get('char_count',12000)
    if type(limit) is not int or not 1<=limit<=20000:raise ValueError('每次1至20000字符')
    lines=source.splitlines(keepends=True)
    if 'start_char' in args:
        start=args['start_char']
        if type(start) is not int or not 0<=start<=len(source):raise ValueError('字符偏移越界')
        stop=len(source);line=source[:start].count('\n')+1
    else:
        start=sum(map(len,lines[:line-1]));selected=lines[line-1:line-1+count]
        stop=start+sum(map(len,selected))
        if selected:stop-=len(selected[-1])-len(selected[-1].rstrip('\r\n'))
    end=min(stop,start+limit)
    if end==start and start<len(source) and source[start]=='\n':end+=1
    return dict(characters=len(source),total_lines=len(lines),start_line=line,start_char=start,text=source[start:end],next_char=end if end<len(source) else None)
