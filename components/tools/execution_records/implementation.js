import { object, str } from "../../../adapters/harness/framework/primitives.js";
import { IncidentStore, RuntimeDiagnostics } from "./store.js";
import { assertCompleteOutput } from "../../../adapters/harness/framework/response-status.js";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { here, user } from "../../../adapters/harness/framework/primitives.js";
import { JsonState } from '../../../adapters/harness/framework/json-state.js';
export function define(r) {}
export const steps = [{
  order: 29,
  async run(r) {
    r.pluginVersion = JSON.parse(await readFile(path.join(here, 'package.json'), 'utf8')).version;
  }
}, {
  order: 30,
  async run(r) {
    r.executionState = new JsonState(path.join(r.directory, 'execution-records'), {
      incidents: [],
      runs: []
    });
    r.incidentStore = new IncidentStore(r.executionState, r.directory, r.pluginVersion, id => r.experienceStore.query({
      ids: [id],
      status: 'all'
    }));
  }
}, {
  order: 31,
  async run(r) {
    await r.incidentStore.recover();
  }
}, {
  order: 35,
  async run(r) {
    r.diagnostics = new RuntimeDiagnostics(r.incidentStore, r.reports,(ac,event,fn)=>r.components.on("tools/execution_records",ac,event,fn));
  }
}];
export function install(r) {
  r.components.on("tools/execution_records", r.ctx, 'datanet/agent-tools', ({
    ac,
    actor,
    role,
    refs,
    view
  }) => {
    r.registerPrivate(ac, 'incident_query', '查询自动收集的阻塞和执行异常，包括未解决现象与重试记录；它们不是已验证经验。', object({
      status: {
        type: 'string',
        enum: ['all', 'unresolved', 'resolved']
      },
      node_id: str,
      query: str,
      offset: {
        type: 'integer',
        minimum: 0
      },
      limit: {
        type: 'integer',
        minimum: 1,
        maximum: 10
      }
    }), async p => ({
      incidents: await r.incidentStore.query(p),
      retry_runs: ((await r.executionState.read()).runs ?? []).filter(r => r.source === r.directory && (!p.node_id || r.node_id === p.node_id)).slice(-(p.limit ?? 6))
    }));
  });
  r.components.on("tools/execution_records", r.ctx, 'datanet/agent-tools', ({
    ac,
    actor,
    role,
    refs,
    view
  }) => {
    r.registerPrivate(ac, 'incident_resolve', '报告者、管理者或获授权经验维护者可标记阻塞已解决。必须提供该节点在报错后正常完成的retry_run_id和具体结果依据；补工具或改提示词本身不能证明解决。可关联待审核或已验证经验ID。', object({
      id: str,
      retry_run_id: str,
      evidence: str,
      experience_id: str
    }, ['id', 'retry_run_id', 'evidence']), async p => {
      const result = await r.incidentStore.resolve(p, actor, r.scopes.get(ac).grant.framework.has('experience_review'), nodeId => r.recoveryAgents[nodeId]?.manager_id ?? null);
      const incident = (await r.incidentStore.query({
        status: 'resolved',
        limit: 10,
        query: p.id
      })).find(x => x.id === p.id);
      if (incident?.feedback_id) await r.problemChannel.recoveryResolved(incident.node_id, incident.feedback_id);
      return result;
    });
  });
  r.components.on("tools/execution_records", r.ctx, 'datanet/agent-bound', ({
    ac,
    agent,
    actor,
    role
  }) => {
    r.diagnostics.attach(ac, agent, () => ({
      node_id: actor,
      manager_id: r.recoveryAgents[actor]?.manager_id ?? null,
      creator_node_id: r.recoveryAgents[actor]?.creator_node_id ?? null,
      role: role ?? null,
      toolboxes: r.scopes.get(ac).grant.names
    }));
    if (actor !== 'root') r.components.on("tools/execution_records", ac, 'agent/status', async ({
      status,
      agent: subject
    }) => {
      if (subject && subject !== agent || status !== 'idle' || !r.messageDriven.has(ac)) return;
      r.messageDriven.delete(ac);
      const state = r.diagnostics.states.get(ac);
      try {
        if (state?.run) {
          assertCompleteOutput(r.diagnostics.messages(ac));
          r.assertProblemClosed(ac);
          await r.diagnostics.completed(ac, '消息处理结束');
        }
      } catch (error) {
        await r.diagnostics.exception(ac, error);
        await r.interruptProblem(ac, error);
      } finally {
        await r.ctx.sessions.flush(agent.session);
        await r.bridge.call('agent_progress', {
          target: actor,
          activity: state?.failed ? 'blocked' : 'idle'
        });
      }
    });
    // Native root is not driven by our delegation wrapper; record its idle outcome separately.
    // Native root is not driven by our delegation wrapper; record its idle outcome separately.
    if (actor === 'root') {
      r.components.on("tools/execution_records", ac, 'agent/request', async (payload, next) => {
        if (!payload.agent || payload.agent === agent) {
          await r.ctx.sessions.flush(agent.session);
          await r.bridge.call('agent_progress', {
            target: actor,
            activity: 'running'
          });
        }
        return next();
      });
      r.components.on("tools/execution_records", ac, 'agent/status', async ({
        status,
        agent: subject
      }) => {
        if (subject && subject !== agent) return;
        if (status !== 'idle') return;
        const state = r.diagnostics.states.get(ac);
        try {
          if (!state?.run) return;
          const messages = agent.session.deriveMessages().slice(state.startIndex);
          const final = messages.filter(m => m.role === 'assistant').at(-1);
          const result = (final?.content ?? []).filter(x => x.type === 'text').map(x => x.text).join('');
          try {
            assertCompleteOutput(messages);
            if (!result.trim()) throw new Error('执行停止，未得到完成结果');
            r.assertProblemClosed(ac);
            await r.diagnostics.completed(ac, result);
          } catch (error) {
            await r.diagnostics.exception(ac, error, 'stopped');
            await r.interruptProblem(ac, error);
          }
        } finally {
          await r.ctx.sessions.flush(agent.session);
          await r.bridge.call('agent_progress', {
            target: actor,
            activity: state?.failed && r.reports.run(ac).run?.status === 'blocked' ? 'blocked' : 'idle'
          });
        }
      });
    }
  });
  r.components.on("tools/execution_records", r.ctx, 'datanet/tool-error', ({
    ac,
    name,
    error
  }) => {
    r.diagnostics.failure(ac, name, error);
  });
}
export function fallback(r) {
  r.diagnostics = {
    states: new WeakMap(),
    metadata: () => null,
    messages: () => [],
    start: async () => {},
    completed: async () => {},
    exception: async () => {},
    failure() {},
    lastCompleted: () => undefined
  };
  r.incidentStore = {
    record: async () => {}
  };
}
