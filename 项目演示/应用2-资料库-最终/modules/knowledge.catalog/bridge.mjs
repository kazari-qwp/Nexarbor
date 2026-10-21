// Thin JSON transport; algorithms below are unmodified upstream TypeScript.
import {analyzeGraph} from './vendor/src/lib/graph.ts';
import {bm25Search} from './vendor/src/lib/search.ts';
let input='';
for await (const chunk of process.stdin) input+=chunk;
const {operation,pages,query,limit=10}=JSON.parse(input);
if(operation==='search') {
  console.log(JSON.stringify({items:bm25Search(pages,query,limit).map(({page,score})=>({slug:page.slug,title:page.title,score}))}));
} else if(operation==='lint') {
  const result=analyzeGraph(pages);
  console.log(JSON.stringify({nodes:result.nodes,edges:result.edges,orphans:result.orphans,
    wantedPages:Object.fromEntries(result.wantedPages),communities:Object.fromEntries(result.communities)}));
} else throw new Error('Unsupported Wiki operation');
