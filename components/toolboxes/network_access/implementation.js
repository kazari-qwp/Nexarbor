import { readFile } from "node:fs/promises";
import path from "node:path";
import { here, object, str, number, readRequest } from "../../../adapters/harness/framework/primitives.js";
export function define(r) {}
export const steps = [{
  order: 7,
  async run(r) {
    r.sharedAgentRules = await readFile(path.join(here, 'components/toolboxes/network_access/AGENTS.md'), "utf8");
  }
}, {
  order: 90,
  async run(r) {
    r.attachData = (agentCtx, actor, maxStrength = r.config.maxSignalStrength ?? 4) => {
      if (!r.attachedData.has(agentCtx)) {
        r.attachedData.add(agentCtx);
        r.components.section("toolboxes/network_access", agentCtx, {
          name: "datanet:shared-agent-rules",
          order: 85,
          interpolate: false,
          text: r.sharedAgentRules
        });
      }
      const discovered = new Set();
      const call = async (method, p) => {
        const strength = p.strength ?? maxStrength;
        if (strength > maxStrength) throw new Error(`Maximum signal strength: ${maxStrength}`);
        const result = await r.bridge.call(method, {
          ...p,
          strength,
          actor
        });
        if (method === 'list_nodes') for (const item of result.items ?? []) item.has_agent = item.node_id === 'root' ? Boolean(r.rootAgent) : r.sessions.has(item.node_id);
        const state = r.sessions.get(actor)?.state;
        if (method === 'write' && state?.final && p.target === state.expectedOutput && p.key === 'content' && p.mode !== 'append' && typeof p.value === 'string' && p.value.trim() && result.status === 'ok') {
          state.outputWritten = true;
          await r.reports.artifact(agentCtx, p.value);
        }
        return result;
      };
      r.registerPrivate(agentCtx, 'node_read', '从所属节点出发读取网络数据，仍检查接口权限。文本用method=key,key=content；可以选target筛选可达目标。', object({
        request: readRequest,
        target: str,
        strength: number,
        scope: {
          type: 'string',
          enum: ['local', 'network']
        }
      }, ['request']), p => call('read', p));
      r.registerPrivate(agentCtx, 'node_write', '从所属节点出发向可写目标写入。', object({
        target: str,
        key: str,
        value: {},
        mode: {
          type: 'string',
          enum: ['upsert', 'append']
        },
        strength: number
      }, ['target', 'key', 'value']), p => call('write', p));
      const scanGrant = r.scopes.get(agentCtx).grant.framework.get('network_structure') ?? {};
      const maxDepth = scanGrant.max_depth ?? 100;
      r.registerPrivate(agentCtx, 'network_structure', `从所属节点查看连接摘要，默认使用最大depth，起点第0层，每个接口计1层；最大depth=${maxDepth}表示查看全部获准拓扑。只查看结构，不扩大数据或操作权限。`, object({
        depth: {
          type: 'integer',
          minimum: 0,
          maximum: maxDepth
        },
        direction: {
          type: 'string',
          enum: ['read', 'write', 'both']
        }
      }), p => {
        const depth = p.depth ?? maxDepth;
        if (!Number.isInteger(depth) || depth < 0 || depth > maxDepth) throw new Error('Invalid scan depth');
        return r.bridge.call('network_structure', {
          actor,
          direction: p.direction ?? 'read',
          depth,
          max_depth: maxDepth,
          inspect_private: scanGrant.inspect_private ?? false
        });
      });
      r.registerPrivate(agentCtx, 'node_list', '发现所属节点可达的节点。', object({
        strength: number
      }), p => call('list_nodes', p));
      r.registerPrivate(agentCtx, 'node_tools', '该节点向你暴露允许你使用的工具，这并不是该节点的工具列表', object({
        target: str,
        strength: number,
        direction: {
          type: 'string',
          enum: ['read', 'write']
        }
      }, ['target']), async p => {
        const result = await call('list_tools', p);
        if (result.status === 'ok') {
          if (result.items.length === 0) return '该节点并未有向你开放的工具';
          for (const item of result.items) discovered.add(JSON.stringify([p.target, p.direction ?? 'read', item.name]));
        }
        return result;
      });
      r.registerPrivate(agentCtx, 'node_invoke', '按已发现定义调用可达节点工具。', object({
        target: str,
        tool: str,
        arguments: {
          type: 'object'
        },
        strength: number,
        direction: {
          type: 'string',
          enum: ['read', 'write']
        }
      }, ['target', 'tool', 'arguments']), p => {
        if (!discovered.has(JSON.stringify([p.target, p.direction ?? 'read', p.tool]))) throw new Error('Discover the exposed node tool first');
        return call('invoke_tool', p);
      });
    };
  }
}];
export function fallback(r) {
  r.attachedData=new WeakSet();
  r.attachData = () => {};
}

export function install(r){r.components.on('toolboxes/network_access',r.ctx,'datanet/agent-bound',({ac,actor})=>{r.attachData(ac,actor,r.scopes.get(ac).maxStrength);});}
