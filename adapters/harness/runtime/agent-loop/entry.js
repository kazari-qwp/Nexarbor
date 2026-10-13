import AgentLoop from './lib/index.js';
export const inject=AgentLoop.inject;
export async function apply(ctx,config={}){
  const original=ctx.get('loader')?.entries?.().find(entry=>entry.id==='agent-loop'&&entry.disabled)?.config??{};
  await ctx.plugin(AgentLoop,{...original,...config,agents:config.agents??original.agents??[]});
}
export default {inject,apply};
export * from './lib/index.js';
