import { ReportStore } from "./store.js";
import { ReportChannel } from "./channel.js";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { here } from "../../../adapters/harness/framework/primitives.js";
export function define(r) {
  r.delegateReport = async function (ac, target, task, receiver, extra = {}) {
    await r.diagnostics.start(ac);
    const previous = r.reports.run(receiver)?.run;
    const delegation = await r.reports.delegate(ac, {
      target,
      task,
      receiver,
      ...extra,
      ...(previous && ['failed', 'blocked', 'interrupted'].includes(previous.status) ? {
        retry_of: previous.run_id
      } : {})
    });
    await r.ctx.serial("datanet/delegated",{ac,delegation,target});
    return delegation;
  };
}
export const steps = [{
  order: 32,
  async run(r) {
    r.reports = new ReportStore(path.join(r.directory, 'reports'));
  }
}, {
  order: 33,
  async run(r) {
    await r.reports.init();
  }
}, {
  order: 34,
  async run(r) {
    r.reportGuide = await readFile(path.join(here, 'components/tools/reports/guides/datanet_reports/AGENTS.md'), 'utf8');
  }
}, {
  order: 76,
  async run(r) {
    r.reportChannel = new ReportChannel(r.reports, {
      actor: ac => r.scopes.get(ac)?.actor,
      load: r.loadInstructions,
      register: r.register,
      enter:(ac,p,next)=>r.ctx.waterfall("datanet/report-channel-enter",{ac,arguments:p},next),
      guide: r.reportGuide
    });
  }
}];
export function install(r) {
  r.components.on('tools/reports',r.ctx,'datanet/delegated',({ac})=>{r.reportChannel.unlock(ac);});
  r.components.on('tools/reports',r.ctx,'datanet/report-channel-enter',(_detail,next)=>next());
  r.components.on("tools/reports", r.ctx, 'datanet/agent-bound', ({
    ac,
    actor,
    agent
  }) => {
    r.reports.restoreContext(ac, actor, agent.id);
  });
  r.components.on("tools/reports", r.ctx, 'datanet/agent-bound', ({
    ac,
    actor,
    agent
  }) => {
    r.reportChannel.restore(ac);
  });
}
export function fallback(r) {
  r.reports = {
    run: () => ({run:null}),
    context: () => null,
    reference: () => null,
    startRun: async () => null,
    tool: async () => {},
    submission: async () => {},
    finish: async () => {},
    delegate: async () => null,
    archiveGrant: async () => {},
    endDelegation: async () => {},
    artifact: async () => {}
  };
  r.reportChannel = {
    unlock() {},
    restore() {}
  };
  r.delegateReport = async () => null;
}
