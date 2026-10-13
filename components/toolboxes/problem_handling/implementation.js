import { compactFeedback, object, str, user } from "../../../adapters/harness/framework/primitives.js";
import { updateCapabilityTools } from "../../../adapters/harness/framework/capabilities.js";
import { writeFile } from "node:fs/promises";
import { assertCompleteOutput } from "../../../adapters/harness/framework/response-status.js";
import { ProblemChannel, TEMPORARY_PROBLEM_TOOLS } from "./channel.js";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { here } from "../../../adapters/harness/framework/primitives.js";
export function define(r) {
  r.closeProblemTools = function (ac) {
    for (const tool of TEMPORARY_PROBLEM_TOOLS) {
      const dispose = r.privateDisposers.get(ac)?.get(tool);
      if (dispose) {
        dispose();
        r.privateDisposers.get(ac).delete(tool);
        r.registeredTools.get(ac)?.delete(tool);
      }
    }
    r.experienceViews.get(ac)?.clearTransient();
  };
  r.interruptProblem = async function (ac, error) {
    await r.problemChannel.abandon(ac, error);
    r.closeProblemTools(ac);
  };
  r.assertProblemClosed = function (ac) {
    if (r.problemChannel.state(ac)) throw new Error('PROBLEM_UNRESOLVED: resolve, defer with task impact, or report a task blocker before completing the task');
  };
}
export const steps = [{
  order: 26,
  async run(r) {
    r.recoveryLimitsGuide = await readFile(path.join(here, 'components/toolboxes/problem_handling/docs/RECOVERY_LIMITS.md'), 'utf8');
  }
}, {
  order: 36,
  async run(r) {
    r.problemChannel = new ProblemChannel(r.experienceStore, r.directory, await readFile(path.join(here, 'components/toolboxes/problem_handling/docs/AGENTS.md'), 'utf8'));
  }
}, {
  order: 37,
  async run(r) {
    await r.problemChannel.recover();
  }
}, {
  order: 69,
  async run(r) {
    for (const report of r.saved.feedback ?? []) {
      await r.incidentStore.record({
        type: 'blocked',
        node_id: report.actor,
        feedback_id: report.id,
        manager_id: r.recoveryAgents[report.actor]?.manager_id ?? null,
        creator_node_id: report.creator_node_id,
        category: report.category,
        message: report.message,
        role: r.saved.agents[report.actor]?.experienceRole ?? r.saved.agents[report.actor]?.role ?? null,
        toolboxes: r.saved.agents[report.actor]?.toolboxes ?? [],
        session_id: r.saved.agents[report.actor]?.session_id ?? null,
        recovered: true
      });
      r.feedbackByAgent.set(report.actor, report);
      if (r.recoveryAgents[report.actor]?.manager_id) {
        const managerId = r.recoveryAgents[report.actor].manager_id;
        r.feedbackUnlockedActors.add(managerId);
        const inbox = r.feedbackInbox.get(managerId) ?? [];
        inbox.push(report);
        r.feedbackInbox.set(managerId, inbox);
      }
    }
  }
}];
export async function install(r) {
  await channels(r);
  r.components.on('toolboxes/problem_handling',r.ctx,'datanet/feedback-received',async({report})=>{
      if (r.recoveryAgents[report.actor]?.manager_id) {
        const managerId = r.recoveryAgents[report.actor].manager_id;
        r.feedbackUnlockedActors.add(managerId);
        const inbox = r.feedbackInbox.get(managerId) ?? [];
        inbox.push(report);
        r.feedbackInbox.set(managerId, inbox);
        const creator = r.sessions.get(managerId)?.handle.agent ?? (managerId === 'root' ? r.rootAgent : null);
        if (creator?.ctx) await r.enterToolChannel(creator.ctx, 'datanet_resolve_feedback');
        if (creator?.status !== 'idle' && creator?.steer) creator.steer(user('下属任务已阻塞并停止。先判断对当前委托的影响；可汇总失败结果时正常汇报，不自动转成自身阻塞。需要时按授权处理：' + JSON.stringify(compactFeedback(report))));
      }
  });
  r.components.on("toolboxes/problem_handling", r.ctx, 'datanet/agent-tools', ({
    ac,
    actor,
    role,
    refs,
    view
  }) => {
    r.registerPrivate(ac, 'handle_problem', '遇到影响任务继续的问题，从这里开始处理；按需加载经验查询、获准排障流程和工具。进入不代表上报，也不增加任何业务权限。简单参数错误可正常重试。', object({
      problem: {
        type: 'string',
        maxLength: 240,
        minLength: 1
      },
      origin: {
        type: 'string',
        enum: ['self', 'subordinate', 'dependency'],
        description: '问题归属，不决定是否阻塞当前委托'
      },
      origin_node_id: {
        type: 'string',
        minLength: 1,
        maxLength: 240,
        description: '下属问题必填实际节点ID；外部依赖可省略'
      },
      problem_id: {
        type: 'string',
        description: '重新处理已结束或中断的问题时复用原ID，保留累计尝试'
      },
      max_attempts: {
        type: 'integer',
        minimum: 1,
        maximum: 3,
        description: '默认3，按上级约束可降低；重开只能保持或降低，不能增加'
      }
    }, ['problem', 'origin']), async (p, exec) => {
      const result = await r.problemChannel.enter(ac, p.problem, p);
      const instructionsAdded = r.loadInstructions(ac, 'problem_handling', r.problemChannel.guide);
      const recoveryInstructionsAdded = result.allow_self_repair === true && r.loadInstructions(ac, 'recovery_limits', r.recoveryLimitsGuide);
      if (r.experienceViews.get(ac)?.loaded.size === 0) await r.experienceViews.get(ac).startup();
      await r.prepareAgent(ac, actor);
      r.attachAgentTools(ac, actor, exec.agent);
      return {
        ...result,
        instructions_added: instructionsAdded,
        recovery_instructions_added: recoveryInstructionsAdded,
        tools: [...TEMPORARY_PROBLEM_TOOLS],
        next: '需排障先调用 experience_query；若未解决也不妨碍当前委托，可直接 problem_defer 记录影响并退出。'
      };
    });
  });
  r.components.on("toolboxes/problem_handling", r.ctx, 'datanet/agent-tools', ({
    ac,
    actor,
    role,
    refs,
    view
  }) => {
    r.registerPrivate(ac, 'problem_attempt', '查过经验后开始验证方案。有experience_id代表尝试查询到的经验；不填则自行修复，必须拥有self_repair授权。只使用原有业务工具。', object({
      experience_id: str
    }), p => r.problemChannel.attempt(ac, p.experience_id));
  });
  r.components.on("toolboxes/problem_handling", r.ctx, 'datanet/agent-tools', ({
    ac,
    actor,
    role,
    refs,
    view
  }) => {
    r.registerPrivate(ac, 'problem_resolved', '问题已解决且完成实际工具验证后结束排障。填简短依据；自行修复须先提交候选经验。记录成功复用并撤下临时工具，不自动提升常加载。', object({
      evidence: {
        type: 'string',
        minLength: 1,
        maxLength: 1000
      }
    }, ['evidence']), async p => {
      const result = await r.problemChannel.resolve(ac, p.evidence);
      r.closeProblemTools(ac);
      return result;
    });
  });
  r.components.on("toolboxes/problem_handling", r.ctx, 'datanet/agent-tools', ({
    ac,
    actor,
    role,
    refs,
    view
  }) => {
    r.registerPrivate(ac, 'problem_defer', '结束本次排障但不标记解决。仅当当前委托仍可继续或允许交付失败结果时使用；必须记录原因、未解决影响及继续/交付依据。保留尝试记录与提示，不报错、不结束任务、不计成功经验。', object({
      reason: {
        type: 'string',
        minLength: 1,
        maxLength: 1000
      },
      impact: {
        type: 'string',
        minLength: 1,
        maxLength: 1000
      },
      continuation: {
        type: 'string',
        minLength: 1,
        maxLength: 1000,
        description: '说明为何未解决仍可履行当前委托，以及下一步如何正常交付'
      }
    }, ['reason', 'impact', 'continuation']), async p => {
      const result = await r.problemChannel.defer(ac, p);
      r.closeProblemTools(ac);
      return result;
    });
  });
  r.components.on("toolboxes/problem_handling", r.ctx, 'datanet/agent-capabilities', ({
    ac,
    actor,
    role
  }) => {
    r.problemChannel.bind(ac, () => r.diagnostics.metadata(ac) ?? {
      node_id: actor,
      role: role ?? null,
      manager_id: r.recoveryAgents[actor]?.manager_id ?? null,
      creator_node_id: r.recoveryAgents[actor]?.creator_node_id ?? null,
      toolboxes: r.scopes.get(ac).grant.names
    }, r.scopes.get(ac).grant.framework.get('handle_problem')?.allow_self_repair === true);
  });
  r.components.on("toolboxes/problem_handling", r.ctx, 'datanet/agent-capabilities', ({
    ac
  }) => {
    if(r.problemGuardScopes.has(ac))return;r.problemGuardScopes.add(ac);
    r.components.guard("toolboxes/problem_handling", ac, exec => r.problemChannel.guard(ac, exec));
  });
  r.components.on("toolboxes/problem_handling", r.ctx, 'datanet/agent-capabilities', ({
    ac
  }) => {
    if(r.problemFlowScopes.has(ac))return;r.problemFlowScopes.add(ac);
    r.components.section("toolboxes/problem_handling", ac, {
      name: 'datanet:problem-flow',
      order: 87,
      interpolate: false,
      text: () => r.problemChannel.render(ac)
    });
  });
  r.components.on("toolboxes/problem_handling", r.ctx, 'datanet/agent-tools', ({
    agentCtx,
    actor,
    parent,
    access
  }) => {
    r.registerPrivate(agentCtx, 'datanet_feedback', '仅当未解决问题确实阻塞自身当前委托时上报并停止。必填task_blocker说明无法继续或交付的原因；下属失败不自动等于自身阻塞。missing_tool/permission_denied使用固定短文本，只有other填写message。可交付失败结果时用problem_defer后正常汇报。', object({
      category: {
        type: 'string',
        enum: ['missing_tool', 'permission_denied', 'other']
      },
      message: {
        type: 'string',
        minLength: 1,
        maxLength: 80,
        description: '仅other填写的简短错误，最多80字。'
      },
      task_blocker: {
        type: 'string',
        minLength: 1,
        maxLength: 1000,
        description: '说明该问题为何阻塞我当前受托任务，而非仅转发下属错误'
      }
    }, ['category', 'task_blocker']), async (p, exec) => {
      r.problemChannel.canReport(agentCtx, p.task_blocker);
      const report = await r.bridge.call('report_feedback', {
        category: p.category,
        ...(p.message ? {
          message: p.message
        } : {}),
        actor
      });
      r.feedbackByAgent.set(actor, report);
      try {
        await r.diagnostics.blocked(agentCtx, report);
      } catch (error) {
        await r.trace({
          type: 'incident_capture_error',
          actor,
          feedback_id: report.id,
          error: String(error.message)
        });
      }
      await r.ctx.serial('datanet/feedback-received',{report});
      const state = r.sessions.get(actor)?.state;
      if (state) state.error = 'AGENT_BLOCKED: ' + actor + ' ' + report.message;
      await r.trace({
        type: 'agent_feedback',
        ...report
      });
      try {
        await r.problemChannel.report(agentCtx, report.id, p.task_blocker);
      } finally {
        r.closeProblemTools(agentCtx);
        exec.concludeTurn();
      }
      return compactFeedback(report);
    });
  });
  r.components.on("toolboxes/problem_handling", r.ctx, 'datanet/agent-tools', ({
    agentCtx,
    actor,
    parent,
    access
  }) => {
    r.registerPrivate(agentCtx, 'datanet_resolve_feedback', '仅限处理`datanet_feedback`的通道:管理者查看并修复真实报错节点，可补充指令、职责或工具箱。', object({
      target: str,
      action: {
        type: 'string',
        enum: ['inspect', 'instruct', 'update_prompt', 'add_toolboxes']
      },
      instruction: str,
      prompt: str,
      toolboxes: {
        type: 'array',
        items: {
          type: 'string',
          enum: r.allowedToolboxes
        },
        uniqueItems: true
      }
    }, ['action']), async (p, exec) => {
      p = {
        ...p,
        target: p.target ?? actor
      };
      if (p.target !== actor && !(await r.bridge.call('check_feedback_owner', {
        actor,
        target: p.target
      })).allowed) throw new Error('Not the manager of a reporting Agent');
      const member = r.sessions.get(p.target);
      if (!member) {
        if (p.target === actor && p.action === 'inspect') return {
          node_id: actor,
          manager_id: r.recoveryAgents[actor]?.manager_id ?? null,
          creator_node_id: r.recoveryAgents[actor]?.creator_node_id ?? null,
          toolboxes: r.scopes.get(agentCtx).grant.names
        };
        throw new Error('Reporting Agent is not mounted');
      }
      if (r.managementLocks.has(p.target) || member.handle.agent.status !== 'idle') throw new Error('Reporting Agent is busy');
      r.managementLocks.add(p.target);
      try {
        if (p.action === 'inspect') return {
          node_id: p.target,
          creator_node_id: r.recoveryAgents[p.target]?.creator_node_id,
          toolboxes: member.toolboxes,
          prompt: member.promptState.text,
          feedback: r.feedbackByAgent.has(p.target) ? compactFeedback(r.feedbackByAgent.get(p.target)) : null
        };
        if (p.action === 'instruct') {
          if (!p.instruction?.trim()) throw new Error('Instruction required');
          await r.problemChannel.reserveRecovery(agentCtx, p.target, r.feedbackByAgent.get(p.target)?.id, member.generic ? 'execute' : 'update_prompt');
          if (!member.generic) {
            await writeFile(member.promptPath, member.promptState.text + '\n\n管理者补充职责：' + p.instruction, 'utf8');
            member.promptState.text += '\n\n管理者补充职责：' + p.instruction;
            await r.remember(p.target, {
              ...r.recoveryAgents[p.target],
              prompt: member.promptState.text
            });
            return {
              node_id: p.target,
              status: 'clarified',
              next: '继续调用datanet_discuss恢复该组'
            };
          }
          await r.delegateReport(agentCtx, p.target, p.instruction, member.handle.agent.ctx, {
            kind: 'retry'
          });
          await r.diagnostics.start(member.handle.agent.ctx);
          let timedOut = false;
          const previous = r.feedbackByAgent.get(p.target)?.id;
          const messageStart = member.handle.agent.session.deriveMessages().length;
          const cancel = () => member.handle.agent.cancel('user');
          exec.signal?.throwIfAborted();
          exec.signal?.addEventListener('abort', cancel, {
            once: true
          });
          const timer = setTimeout(() => {
            timedOut = true;
            cancel();
          }, r.config.turnTimeoutMs ?? 180000);
          try {
            member.handle.agent.followup(user(p.instruction));
            await member.handle.agent.whenIdle();
            exec.signal?.throwIfAborted();
            if (timedOut) throw new Error('Agent execution timeout');
            assertCompleteOutput(member.handle.agent.session.deriveMessages().slice(messageStart));
            if (r.feedbackByAgent.get(p.target)?.id === previous && r.diagnostics.states.get(member.handle.agent.ctx)?.failed) throw new Error('Agent execution failed');
            if (r.feedbackByAgent.get(p.target)?.id === previous) {
              r.assertProblemClosed(member.handle.agent.ctx);
              await r.diagnostics.completed(member.handle.agent.ctx, '管理者补充指令后的重试正常返回');
            }
          } catch (error) {
            await r.diagnostics.exception(member.handle.agent.ctx, error);
            await r.interruptProblem(member.handle.agent.ctx, error);
            throw error;
          } finally {
            clearTimeout(timer);
            exec.signal?.removeEventListener('abort', cancel);
            await r.ctx.sessions.flush(member.handle.agent.session);
          }
          const feedback = r.feedbackByAgent.get(p.target);
          const blocked = feedback?.id !== previous;
          await r.bridge.call('agent_progress', {
            target: p.target,
            activity: blocked ? 'blocked' : 'idle'
          });
          return {
            node_id: p.target,
            report_reference: r.reports.reference(r.reports.context(member.handle.agent.ctx)),
            status: blocked ? 'blocked' : 'ok',
            ...(!blocked ? {
              retry_run_id: r.diagnostics.lastCompleted(member.handle.agent.ctx)
            } : {}),
            ...(blocked ? {
              feedback: compactFeedback(feedback)
            } : {}),
            message: member.handle.agent.session.deriveMessages().filter(m => m.role === 'assistant').at(-1) ?? null
          };
        }
        if (p.action === 'update_prompt') {
          if (!p.prompt?.trim()) throw new Error('Prompt required');
          await r.problemChannel.reserveRecovery(agentCtx, p.target, r.feedbackByAgent.get(p.target)?.id, 'update_prompt');
          await writeFile(member.promptPath + '.bak', await readFile(member.promptPath, 'utf8'), 'utf8');
          await writeFile(member.promptPath, p.prompt, 'utf8');
          member.promptState.text = p.prompt;
          await r.remember(p.target, {
            ...r.recoveryAgents[p.target],
            prompt: p.prompt
          });
          return {
            node_id: p.target,
            status: 'updated',
            context_preserved: true
          };
        }
        if (!p.toolboxes?.length) throw new Error('Toolboxes required');
        r.resolveAgentToolboxes(p.toolboxes, r.allowedToolboxes);
        const ac = member.handle.agent.ctx,
          entry = r.scopes.get(ac);
        const grant = r.resolveAgentToolboxes([...new Set([...entry.grant.names, ...p.toolboxes])], undefined, {
          role: r.recoveryAgents[p.target]?.kind
        });
        // Official Skill registry masks cannot be removed through the current adapter.
        if (JSON.stringify(grant.official.skills) !== JSON.stringify(entry.grant.official.skills) || JSON.stringify(grant.official.skillProviders) !== JSON.stringify(entry.grant.official.skillProviders)) throw new Error('Runtime official Skill grant changes are not supported; tools can be added');
        await r.problemChannel.reserveRecovery(agentCtx, p.target, r.feedbackByAgent.get(p.target)?.id, 'add_toolboxes');
        const official = updateCapabilityTools(ac, member.handle.agent, grant.official, r.ctx, r.permissions);
        entry.grant = grant;
        r.messaging.refresh(p.target);
        await r.prepareAgent(ac, p.target);
        r.attachData(ac, p.target, entry.maxStrength);
        r.attachAgentTools(ac, p.target, member.handle.agent);
        member.toolboxes = grant.names;
        member.baseToolboxes = [...new Set([...(member.baseToolboxes ?? r.recoveryAgents[p.target].toolboxes), ...p.toolboxes])];
        await r.remember(p.target, {
          ...r.recoveryAgents[p.target],
          toolboxes: member.baseToolboxes
        });
        await r.trace({
          type: 'repair_toolboxes',
          actor,
          target: p.target,
          toolboxes: p.toolboxes
        });
        return {
          node_id: p.target,
          status: 'updated',
          context_preserved: true,
          toolboxes: grant.names,
          unavailable_tools: official.unavailableTools
        };
      } finally {
        r.managementLocks.delete(p.target);
      }
    });
  });
  r.components.on("toolboxes/problem_handling", r.ctx, 'datanet/agent-tools', ({
    agentCtx,
    actor,
    parent,
    access
  }) => {
    r.registerPrivate(agentCtx, 'datanet_recovery_status', '查看已恢复 Agent、网络讨论状态和中断时结果不明的操作；这些操作不会自动重放。', object(), async () => {
      r.loadInstructions(agentCtx, 'tool:datanet_recovery_status', r.recoveryGuide);
      const status = await r.bridge.call('recovery_info');
      return {
        ...status,
        feedback: (status.feedback ?? []).map(compactFeedback),
        agents: Object.fromEntries(Object.entries(status.agents ?? {}).map(([key, value]) => [key, {
          session_id: value.session_id ?? null,
          kind: value.kind ?? null,
          toolboxes: value.toolboxes ?? [],
          manager_id: value.manager_id ?? null,
          managed_ids: value.managed_ids ?? [],
          creator_node_id: value.creator_node_id ?? null,
          activity: value.activity ?? null,
          count: value.count ?? null
        }])),
        mounted_agents: [...r.sessions.keys()],
        recovery_budgets: await r.problemChannel.recoveryStatus(),
        errors: r.recoveryErrors
      };
    });
  });
  r.components.on("toolboxes/problem_handling", r.ctx, 'datanet/agent-tools', ({
    agentCtx,
    actor
  }) => {
    if (!r.feedbackSections.has(agentCtx)) {
      r.feedbackSections.add(agentCtx);
      r.components.section("toolboxes/problem_handling", agentCtx, {
        name: 'datanet:feedback-inbox',
        order: 89,
        interpolate: false,
        text: () => {
          const reports = r.feedbackInbox.get(actor) ?? [];
          return `管理者节点：${r.recoveryAgents[actor]?.manager_id ?? '无（根 Agent，反馈给用户）'}。` + (reports.length ? '\n下属阻塞反馈（历史记录，不代表已解决）：\n' + JSON.stringify(reports.map(compactFeedback)) : '');
        }
      });
    }
  });
  r.components.on("toolboxes/problem_handling", r.ctx, 'datanet/agent-bound', ({
    ac,
    agent
  }) => {
    r.components.on("toolboxes/problem_handling", ac, 'tools/result', async (exec, result) => {
      if (exec.agent && exec.agent !== agent) return;
      await r.problemChannel.outcome(ac, exec, result);
    });
  });
  r.components.on("toolboxes/problem_handling", r.ctx, 'datanet/agent-bound', ({
    ac,
    agent
  }) => {
    r.components.on("toolboxes/problem_handling", ac, 'agent/error', async payload => {
      if (payload.agent && payload.agent !== agent) return;
      await r.interruptProblem(ac, payload.error ?? 'agent error');
    });
  });
  r.components.on("toolboxes/problem_handling", r.ctx, 'datanet/agent-bound', ({
    ac,
    agent
  }) => {
    r.components.on("toolboxes/problem_handling", ac, 'agent/turn-stopping', payload => {
      if (payload.agent && payload.agent !== agent) return;
      if (r.problemChannel.state(ac)) agent.steer(user('当前排障尚未结束：实际修好用 problem_resolved；未解决但当前委托可继续或交付失败结果，用 problem_defer 保留影响后正常汇报；确实阻塞自身委托才用 datanet_feedback。'));
    });
  });
  r.components.on("toolboxes/problem_handling", r.ctx, 'datanet/tool-before', async ({
    ac,
    name,
    arguments: args
  }) => {
    r.problemChannel.assert(ac, {
      name,
      arguments: args
    });
    await r.loadToolExperience(ac, name);
  });
  r.components.on("toolboxes/problem_handling", r.ctx, 'datanet/tool-after', async ({
    ac,
    name,
    exec,
    value
  }) => {
    if (!exec.callId) await r.problemChannel.outcome(ac, {
      name
    }, {
      value
    });
  });
  r.components.on("toolboxes/problem_handling", r.ctx, 'datanet/tool-error', async ({
    ac,
    name,
    exec,
    error
  }) => {
    if (!exec.callId) await r.problemChannel.outcome(ac, {
      name
    }, {
      isError: true,
      content: [{
        type: 'text',
        text: String(error.message ?? error)
      }]
    });
  });
}
export function fallback(r) {
  stateDefaults(r);
  r.problemChannel = {
    state: () => null,
    assert() {},
    render: () => '',
    outcome: async () => {},
    abandon: async () => {},
    reserveRecovery: async () => {},
    recoveryStatus: async () => []
  };
  r.interruptProblem = async () => {};
  r.assertProblemClosed = () => {};
  r.closeProblemTools = () => {};
  r.isTemporaryTool = () => false;
  r.temporaryToolsAllowed=()=>false;
}
export async function channels(r) {
  r.isTemporaryTool = name => TEMPORARY_PROBLEM_TOOLS.has(name);
  r.temporaryToolsAllowed=ac=>!!r.problemChannel.state(ac);
  r.recoveryGuide = await readFile(path.join(here, 'components/toolboxes/problem_handling/guides/datanet_recovery_status/AGENTS.md'), 'utf8');
  r.feedbackGuide = await readFile(path.join(here, 'components/toolboxes/problem_handling/guides/datanet_resolve_feedback/AGENTS.md'), 'utf8');
  r.channelSpecs.set('datanet_resolve_feedback', {
    guide: r.feedbackGuide,
    allowed: ac => r.feedbackUnlockedActors.has(r.scopes.get(ac).actor)
  });
}
export function stateDefaults(r) {
  r.feedbackByAgent = new Map();
  r.feedbackInbox = new Map();
  r.feedbackUnlockedActors = new Set();
  r.feedbackSections = new WeakSet();
  r.problemGuardScopes=new WeakSet();r.problemFlowScopes=new WeakSet();
}
