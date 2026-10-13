import { SharedTexts } from "./controller.js";
export function define(r) {}
export const steps = [{
  order: 66,
  async run(r) {
    r.sharedTexts = new SharedTexts({
      bridge: r.bridge,
      register: r.register,
      instructions: r.instructionHistory,
      on:(ac,event,fn)=>r.components.on("nodes/text",ac,event,fn),
      scope: ac => r.scopes.get(ac)
    });
  }
}];
export function install(r) {
  r.components.on("nodes/text", r.ctx, 'datanet/agent-bound', ({
    ac,
    agent
  }) => {
    r.sharedTexts.attach(ac, agent);
  });
  r.components.on("nodes/text", r.ctx, 'datanet/graph-changed', async ({
    ac
  }) => {
    await r.sharedTexts.sync(ac);
  });
  r.components.on("nodes/text", r.ctx, 'datanet/discussion-member-start', async ({
    ac,
    group,
    projectIds
  }) => {
    await r.sharedTexts.project(ac, group, projectIds);
  });
}
export function fallback(r) {
  r.sharedTexts = {
    attach() {},
    sync: async () => {}
  };
}
