// Carry only owned unfinished leaf work, including successors from earlier parent turns.
// Public releases remain available through the normal component-revision API.
const boundary=job=>JSON.stringify([...(job.hidden_modules??[])].sort());
export function unfinishedComponents(jobs,current){
 if(current.scoped)return [];
 const history=[...jobs.values()].filter(job=>job.workspace===current.workspace&&job.kind===current.kind&&!job.scoped&&boundary(job)===boundary(current)).sort((a,b)=>(a.started??0)-(b.started??0)),prior=history.at(-1);
 if(!prior)return [];
 const seeds=new Set([...(prior.children??[]),...(prior.inherited_children??[])]),owned=new Set(history.flatMap(job=>[...(job.children??[]),...(job.inherited_children??[])])),relevant=new Set(seeds),superseded=new Set();
 for(const id of owned){
  const chain=[],seen=new Set([id]);let ancestor=jobs.get(id)?.continues_task;
  while(ancestor&&!seen.has(ancestor)){seen.add(ancestor);chain.push(ancestor);ancestor=jobs.get(ancestor)?.continues_task;}
  if(seeds.has(id)||chain.some(ancestor=>seeds.has(ancestor))){relevant.add(id);for(const ancestor of chain)superseded.add(ancestor);}
 }
 return [...relevant].filter(id=>{const child=jobs.get(id);return child&&!child.release&&!superseded.has(id);});
}
