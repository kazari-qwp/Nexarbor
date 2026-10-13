import { assertCompleteOutput } from "../../../adapters/harness/framework/response-status.js";
import { randomUUID } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { applyCapabilities } from "../../../adapters/harness/framework/capabilities.js";
import { resolveToolboxes } from "../../../adapters/harness/framework/toolbox-catalog.js";
import { here, object, str, user, checked } from "../../../adapters/harness/framework/primitives.js";
export function define(r) {
  r.makeMembers = async function (group, parent) {
    for (const actor of group.members) {
      const parentScope = r.scopes.get(parent.ctx);
      if (!(await r.bridge.call('check_management', {
        actor: parentScope.actor,
        target: actor,
        scope: parentScope.grant.framework.get('datanet_create_agent')?.scope ?? 'self'
      })).allowed) throw new Error('Discussion member is outside Agent creation grant');
      const role = actor === group.leader_id ? 'leader' : actor === group.recorder_id ? 'recorder' : 'member';
      const binding = r.recoveryAgents[actor];
      const prompt = binding?.prompt ?? (await readFile(r.agentPresets[role].promptPath, 'utf8'));
      const promptPath = path.join(r.directory, 'agents', Buffer.from(actor).toString('hex') + '.md');
      await mkdir(path.dirname(promptPath), {
        recursive: true
      });
      await writeFile(promptPath, prompt, 'utf8');
      const promptState = {
        text: prompt
      };
      const state = {
        count: binding?.count ?? 0,
        submitted: false,
        error: null,
        final: false,
        scheduled: false
      };
      const sessionId = binding?.session_id ?? 'datanet-' + randomUUID();
      const grant = r.resolveAgentToolboxes(binding?.toolboxes ?? r.discussionToolboxes, r.allowedToolboxes, {
        role: 'discussion'
      });
      const agentOptions = {
        ...(binding?.agentOptions ?? {
          ...r.route(parent.options),
          ...(r.config.provider ? {
            provider: r.config.provider,
            model: r.config.model
          } : {})
        }),
        maxTokens: r.config.agentMaxTokens ?? 4096
      };
      if (!binding) await r.remember(actor, {
        session_id: sessionId,
        kind: 'discussion',
        group_id: group.group_id,
        role,
        creator_node_id: r.scopes.get(parent.ctx)?.actor ?? null,
        prompt,
        promptPath,
        toolboxes: grant.names,
        maxStrength: r.config.discussionMaxSignalStrength ?? 2,
        agentOptions,
        status: 'prepared',
        count: 0
      });
      const handle = await r.openAgent(binding, {
        sessionId,
        parentAgent: parent,
        meta: {
          cwd: r.workspace,
          agentPreset: binding?.officialPreset ?? 'standard'
        },
        agentOptions,
        async setup(ac, agent) {
          r.scopes.set(ac, {
            grant,
            actor,
            maxStrength: r.config.discussionMaxSignalStrength ?? 2
          });
          await r.prepareAgent(ac, actor, role, r.agentPresets[role]?.experience_refs ?? []);
          r.bindAgentContext(ac, agent, actor, role);
          const official = await applyCapabilities(ac, agent, grant.official, r.ctx, binding?.officialPreset, r.permissions);
          await r.remember(actor, {
            ...r.recoveryAgents[actor],
            officialPreset: official.officialPreset
          });
          await r.trace({
            type: 'capabilities',
            actor,
            session: agent.id,
            toolboxes: grant.names,
            ...official
          });
          r.attachData(ac, actor, r.config.discussionMaxSignalStrength ?? 2);
          await r.ctx.serial('datanet/graph-changed', {
            ac: ac
          });
          r.attachAgentTools(ac, actor, agent);
          await r.restoreSkills(ac, agent);
          r.components.section("network_presets/discussion_group", ac, {
            name: 'datanet:role',
            order: 90,
            interpolate: false,
            text: () => `${promptState.text}\n所属节点：${actor}\n当前请求次数：${state.count + 1}/10。必须在第10次前提交或跳过。`
          });
          r.components.on("network_presets/discussion_group", ac, 'agent/pre-step', async (_payload, next) => state.scheduled && state.count >= 10 ? {
            kind: 'reject',
            reason: 'discussion request budget exhausted'
          } : next());
          r.components.on("network_presets/discussion_group", ac, 'agent/request', async (_payload, next) => {
            if (state.scheduled) state.count++;
            await r.ctx.sessions.flush(agent.session);
            await r.bridge.call('agent_progress', {
              target: actor,
              count: state.count,
              activity: 'running'
            });
            await r.trace({
              type: 'request',
              actor,
              count: state.count,
              session: agent.id
            });
            return next();
          });
          r.components.on("network_presets/discussion_group", ac, 'agent/error', payload => {
            state.error = String(payload.error || 'agent error');
          });
          r.components.on("network_presets/discussion_group", ac, 'agent/turn-stopping', () => {
            if (state.scheduled && !state.submitted && !state.final && state.count < 10) agent.steer(user('本轮未完成，请调用 submit_round 或 skip_round。'));
          });
          r.registerPrivate(ac, 'read_round', '读取本组上轮讨论快照；不读取本轮其他人的实时提交。', object(), () => r.bridge.call('read_round', {
            actor,
            group_id: group.group_id,
            strength: r.config.discussionMaxSignalStrength ?? 2
          }));
          r.registerPrivate(ac, 'submit_round', '向公共黑板追加本轮发言并结束本轮。', object({
            content: str
          }, ['content']), async (p, exec) => {
            if (state.final) throw new Error('Finalization has no discussion submission');
            const result = checked(await r.bridge.call('submit', {
              ...p,
              actor,
              group_id: group.group_id
            }));
            state.submitted = true;
            await r.reports.submission(ac, {
              group_id: group.group_id,
              content: p.content,
              skip: false
            });
            await r.trace({
              type: 'submit',
              actor,
              group_id: group.group_id,
              content: p.content
            });
            exec.concludeTurn();
            return result;
          });
          r.registerPrivate(ac, 'skip_round', '明确跳过本轮并结束。', object({
            reason: str
          }, ['reason']), async (p, exec) => {
            if (state.final) throw new Error('Finalization has no discussion submission');
            const result = checked(await r.bridge.call('submit', {
              content: p.reason,
              skip: true,
              actor,
              group_id: group.group_id
            }));
            state.submitted = true;
            await r.reports.submission(ac, {
              group_id: group.group_id,
              content: p.reason,
              skip: true
            });
            exec.concludeTurn();
            return result;
          });
        }
      });
      r.ctx.sessionTitle.rename(handle.agent.session, 'DataNet · ' + actor);
      await r.ctx.sessions.flush(handle.agent.session);
      await r.remember(actor, {
        ...r.recoveryAgents[actor],
        toolboxes: grant.names,
        status: 'ready',
        activity: binding?.activity === 'running' ? 'interrupted' : 'idle'
      });
      r.sessions.set(actor, {
        handle,
        state,
        actor,
        promptPath,
        promptState,
        toolboxes: r.scopes.get(handle.agent.ctx).grant.names,
        maxStrength: r.config.discussionMaxSignalStrength ?? 2
      });
      r.messaging.attach(actor, handle.agent);
    }
  };
  r.drive = async function (member, text, signal) {
    const {
      handle,
      state
    } = member;
    const messageStart = handle.agent.session.deriveMessages().length;
    if (!member.resumeBudget) state.count = 0;
    member.resumeBudget = false;
    state.error = null;
    state.submitted = false;
    await r.problemChannel.reserveRecovery(member.handle.agent.ctx, member.actor, r.feedbackByAgent.get(member.actor)?.id, 'execute');
    await r.diagnostics.start(handle.agent.ctx);
    let timedOut = false;
    const cancel = () => handle.agent.cancel('user');
    signal?.throwIfAborted();
    signal?.addEventListener('abort', cancel, {
      once: true
    });
    const timer = setTimeout(() => {
      timedOut = true;
      cancel();
    }, r.config.turnTimeoutMs || 180000);
    try {
      state.scheduled = true;
      handle.agent.followup(user(text));
      await handle.agent.whenIdle();
      signal?.throwIfAborted();
      if (timedOut) throw new Error('Agent execution timeout');
      if (state.error) throw new Error(state.error);
      assertCompleteOutput(handle.agent.session.deriveMessages().slice(messageStart));
      r.assertProblemClosed(handle.agent.ctx);
      await r.diagnostics.completed(handle.agent.ctx, '讨论成员完成当前调度');
    } catch (error) {
      await r.diagnostics.exception(handle.agent.ctx, error);
      await r.interruptProblem(handle.agent.ctx, error);
      throw error;
    } finally {
      state.scheduled = false;
      clearTimeout(timer);
      signal?.removeEventListener('abort', cancel);
      await r.ctx.sessions.flush(handle.agent.session);
      await r.bridge.call('agent_progress', {
        target: member.actor,
        activity: state.error?.startsWith('AGENT_BLOCKED:') ? 'blocked' : 'idle'
      });
    }
  };
}
export const steps = [{
  order: 4,
  async run(r) {
    for (const value of [r.config.maxSignalStrength ?? 4, r.config.discussionMaxSignalStrength ?? 2]) if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) throw new Error('Signal limits must be finite nonnegative numbers');
  }
}, {
  order: 5,
  async run(r) {
    if ((r.config.discussionMaxSignalStrength ?? 2) > (r.config.maxSignalStrength ?? 4)) throw new Error('Discussion budget exceeds host limit');
  }
}, {
  order: 55,
  async run(r) {
    r.discussionToolboxes = r.config.discussionToolboxes ?? ['network_access', 'discussion_member'];
  }
}, {
  order: 60,
  async run(r) {
    resolveToolboxes(r.toolboxRegistry, r.discussionToolboxes, r.allowedToolboxes);
    // Prompt files are selectable presets; optional same-name JSON supplies defaults and a description.
  }
}];
export function install(r) {
  restoreHook(r);
  r.components.on("network_presets/discussion_group", r.ctx, 'datanet/agent-tools', ({
    agentCtx,
    actor,
    parent,
    access
  }) => {
    r.registerPrivate(agentCtx, 'datanet_discuss', '运行已创建的五人讨论组；每轮10次请求。所有人只看到同一上轮快照，最终由Recorder写成果。', object({
      group_id: str,
      task: str
    }, ['group_id']), async (p, exec) => {
      await access(p.group_id + '/board', 'write');
      const group = r.groups.get(p.group_id);
      if (!group) throw new Error('Group is not mounted in this Harness process');
      if (group.busy) throw new Error('Discussion is already running');
      group.busy = true;
      let discussionReport;
      try {
        const info = await r.bridge.call('group_info', p);
        if (info.completed) return {
          status: 'ok',
          result: await r.bridge.call('read', {
            actor,
            target: info.output_id,
            request: {
              method: 'key',
              key: 'content'
            },
            strength: r.scopes.get(agentCtx).maxStrength
          })
        };
        p = {
          ...p,
          task: p.task ?? info.task
        };
        if (!p.task) throw new Error('New discussion requires a task');
        if (info.task && info.task !== p.task) throw new Error('Recovered discussion must continue its saved task');
        await r.diagnostics.start(agentCtx);
        discussionReport = await r.reports.delegate(agentCtx, {
          target: p.group_id,
          task: p.task,
          kind: 'discussion'
        });
        r.reportChannel.unlock(agentCtx);
        const archiveAgent = r.sessions.get(group.recorder_id);
        await r.reports.archiveGrant(group.recorder_id, discussionReport);
        r.reportChannel.unlock(archiveAgent.handle.agent.ctx);
        const scheduleMember = async (member, text, signal, round) => {
          await r.delegateReport(agentCtx, member.actor, text, member.handle.agent.ctx, {
            parent: discussionReport,
            kind: member.state.final ? 'archive' : 'discussion_member',
            round
          });
          await r.ctx.serial('datanet/discussion-member-start', {
            ac: member.handle.agent.ctx,
            group: p.group_id,
            projectIds: info.project_ids
          });
          return r.drive(member, text, signal);
        };
        await r.bridge.call('group_task', p);
        for (let i = info.busy ? info.round - 1 : info.round; i < info.total; i++) {
          const round = await r.bridge.call('start_round', p);
          for (const actor of group.members) {
            if (Object.hasOwn(round.submitted ?? {}, actor)) continue;
            const member = r.sessions.get(actor);
            member.state.final = false;
            await scheduleMember(member, `项目任务：${p.task}\n当前轮数：${round.round}/${round.total}\n项目资料ID：${info.project_ids.join("、")}；成果ID：${info.output_id}。项目资料已首次加载，后续按需使用绑定查询工具。公共笔记由框架放在请求尾部；Recorder用write_resident_text维护。讨论黑板只用read_round读取；私人笔记为你的节点ID加_notes。\n上轮所有成员发言（共同快照）：\n${round.snapshot}\n若任务只要求测试发言，无需读取其他信息，直接submit_round({"content":"测试"})即可。通常讨论按需访问资料、编辑笔记，最后提交本轮发言或跳过。`, exec.signal, round.round);
            if (!member.state.submitted) throw new Error(`${actor} did not submit within budget`);
          }
          await r.trace({
            type: 'round',
            ...(await r.bridge.call('finish_round', p))
          });
        }
        const finalRound = await r.bridge.call("group_info", p);
        const finalSubmissions = JSON.stringify(finalRound.submitted ?? {}, null, 2);
        const recorder = r.sessions.get(group.recorder_id);
        recorder.state.final = true;
        recorder.state.expectedOutput = info.output_id;
        recorder.state.outputWritten = false;
        await scheduleMember(recorder, `讨论已结束。请根据任务“${p.task}”和历史上下文，以及以下最后一轮全部成员发言（这是归档后的完整提交，须据此汇总，不能只依据轮初快照）：\n${finalSubmissions}\n按当前任务要求归档；需要操作证据时进入 datanet_reports_channel，查询本次讨论委托的报告索引并读取真实报告或工具结果。不要猜测脚本路径、命令或退出码；证据缺失时注明缺失，不补造。把最终成果写入 ${info.output_id}，用node_write、key=content、mode=upsert；然后回复最终结论。`, exec.signal);
        if (!recorder.state.outputWritten) throw new Error('FINAL_OUTPUT_NOT_CONFIRMED: Recorder 本次未成功写入非空最终成果；讨论已完成，请继续收尾，不要重新建组。');
        const result = checked(await r.bridge.call('read', {
          actor,
          target: info.output_id,
          request: {
            method: 'key',
            key: 'content'
          },
          strength: r.scopes.get(agentCtx).maxStrength
        }));
        const output = result.items;
        await r.trace({
          type: 'completed',
          group_id: p.group_id,
          output
        });
        await r.bridge.call('group_complete', p);
        await r.bridge.call('save');
        await r.reports.endDelegation(discussionReport, 'completed');
        return {
          status: 'ok',
          output,
          result,
          report_reference: r.reports.reference(discussionReport)
        };
      } catch (error) {
        if (discussionReport) await r.reports.endDelegation(discussionReport, 'failed', error);
        await r.bridge.call('group_error', {
          group_id: p.group_id,
          error: String(error.message ?? error)
        });
        await r.trace({
          type: 'discussion_error',
          group_id: p.group_id,
          error: String(error.message ?? error)
        });
        throw error;
      } finally {
        group.busy = false;
      }
    });
  });
}
export function fallback(r) {
  r.groups = new Map();
  r.discussionToolboxes = [];
  r.makeMembers = async () => {
    throw new Error('Discussion preset is disabled');
  };
}
export function restoreHook(r) {
  r.components.on('network_presets/discussion_group', r.ctx, 'datanet/restore-agents', async ({
    agent
  }) => {
    for (const group of Object.values(r.saved.groups ?? {})) {
      try {
        if (!r.scopes.get(agent.ctx).grant.framework.has('datanet_create_agent')) throw new Error('Agent restoration disabled by toolboxes');
        await r.makeMembers(group, agent);
        r.groups.set(group.group_id, {
          ...group,
          busy: false
        });
        for (const actor of group.members) r.sessions.get(actor).resumeBudget = group.busy;
      } catch (error) {
        r.recoveryErrors.push({
          group_id: group.group_id,
          error: String(error)
        });
      }
    }
  });
}
