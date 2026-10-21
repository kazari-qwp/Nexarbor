// Line and character windows share one hard size bound, including single-line JSON.
export function textWindow(source,args={}, {defaultLines=100,maxLines=300,keepSeparator=true}={}){
 const line=args.start_line??1,lines=args.line_count??defaultLines;
  if(!Number.isInteger(line)||line<1||!Number.isInteger(lines)||lines<1||lines>maxLines)throw Error('行号从1开始，每次1至'+maxLines+'行');
  const all=source.split('\n');let start;
  if(args.start_char!==undefined){if(!Number.isInteger(args.start_char)||args.start_char<0||args.start_char>source.length)throw Error('字符偏移越界');start=args.start_char;}
  else start=all.slice(0,Math.min(line-1,all.length)).reduce((count,text)=>count+text.length+1,0);
  start=Math.min(start,source.length);
  const limit=args.char_count??12000;if(!Number.isInteger(limit)||limit<1||limit>20000)throw Error('每次1至20000字符');
  const lineEnd=args.start_char===undefined?Math.min(source.length,start+all.slice(line-1,line-1+lines).join('\n').length):source.length;
  if(start>0&&/[\uDC00-\uDFFF]/.test(source[start])&&/[\uD800-\uDBFF]/.test(source[start-1]))throw Error('字符偏移位于 Unicode 字符内部，请沿 next_char 翻页');
  let end=Math.min(lineEnd,start+limit);if(end>start&&/[\uD800-\uDBFF]/.test(source[end-1]))end--;
  if(end===start&&start<source.length&&lineEnd>start)throw Error('字符窗口太小，请至少读取2字符');
  // Preserve a separating newline when the requested line window has more data.
  if(keepSeparator&&end===lineEnd&&lineEnd<source.length&&end<start+limit&&source[end]==='\n')end++;
  if(end===start&&start<source.length&&source[start]==='\n')end++;
  const next=end<source.length?end:null;

 return {characters:source.length,total_lines:all.length,start_line:args.start_char===undefined?line:source.slice(0,start).split('\n').length,start_char:start,text:source.slice(start,end),next_char:next};
}
