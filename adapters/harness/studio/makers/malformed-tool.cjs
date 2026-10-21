// Report only structure metadata from the failed attempt, never argument values.
module.exports=events=>{
 const attempts=events.filter(event=>event.type==='assistant/attempt'),found=[];
 for(const part of attempts.at(-1)?.data?.stream??[]){
  const block=part.chunk?.block;
  if(block?.type!=='tool-call'||typeof block.arguments!=='string')continue;
  try{JSON.parse(block.arguments);}catch(error){
   const position=/position\s+(\d+)/i.exec(error.message);
   found.push({tool:block.name,characters:block.arguments.length,position:position?Number(position[1]):null});
  }
 }
 return found;
};
