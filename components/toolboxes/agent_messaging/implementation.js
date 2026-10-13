import { MessageRouter } from "./router.js";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { createUserMessage } from "@deepseek-ai/dsh-llm";
import { here } from "../../../adapters/harness/framework/primitives.js";
export function define(r) {}
export const steps = [{
  order: 70,
  async run(r) {
    r.messageDriven = new WeakSet();
  }
}, {
  order: 71,
  async run(r) {
    r.messaging = new MessageRouter(path.join(r.directory, 'communications'), {
      on:(ac,event,fn)=>r.components.on("toolboxes/agent_messaging",ac,event,fn),
      section:(ac,def)=>r.components.section("toolboxes/agent_messaging",ac,def),
      received:detail=>r.ctx.emit("datanet/message-received",detail),
      bindings: () => r.recoveryAgents,
      register: r.register,
      canSend: actor => {
        const agent = actor === 'root' ? r.rootAgent : r.sessions.get(actor)?.handle.agent;
        return r.scopes.get(agent?.ctx)?.grant.framework.has('datanet_send_message') ?? false;
      },
      guide: await readFile(path.join(here, 'components/toolboxes/agent_messaging/guides/datanet_messages/AGENTS.md'), 'utf8'),
      load: r.loadInstructions,
      ttl: r.config.messageReplyTimeoutMs ?? 30 * 60 * 1000,
      message: (sender, e) => createUserMessage({
        source: {
          kind: 'agent-message',
          form: 'relay',
          senderSessionId: sender.id
        },
        content: [{
          type: 'text',
          text: JSON.stringify({
            type: e.reply_to ? 'reply' : 'message',
            from: e.from,
            communication_id: e.communication_id,
            message_id: e.id,
            ...(e.reply_to ? {
              reply_to: e.reply_to
            } : {}),
            reply_tool: e.reply_tool,
            content: e.content
          })
        }]
      }),
      onWake: (actor, agent) => {
        if (actor !== 'root') r.messageDriven.add(agent.ctx);
      },
      onError: error => r.trace({
        type: 'message_delivery_error',
        error: String(error.message ?? error)
      })
    });
  }
}, {
  order: 72,
  async run(r) {
    await r.messaging.init();
  }
}, {
  order: 73,
  async run(r) {
    const messaging=r.messaging;r.components.track('toolboxes/agent_messaging',()=>messaging.close());
  }
}];
export function fallback(r) {
  r.messageDriven = new WeakSet();
  r.messaging = {
    attach() {},
    refresh() {},
    close() {},
    manages: (...args) => r.managesAgent(...args)
  };
}

export function install(r){r.components.on('toolboxes/agent_messaging',r.ctx,'datanet/agent-ready',({actor,agent})=>{r.messaging.attach(actor,agent);});r.components.on('toolboxes/agent_messaging',r.ctx,'datanet/message-received',({actor})=>{r.messaging.refresh(actor);});}
export async function uninstall(r){await r.messaging.close();}
