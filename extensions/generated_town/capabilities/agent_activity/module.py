from datanet.studio.contract import StudioModule


class Module(StudioModule):
    """在 world.tick 时驱动本节点的原生 Agent 执行端口。"""

    def setup(self):
        self.state.setdefault('processed_signal_ids', [])
        self.state.setdefault('last_signal_id', None)
        self.state.setdefault('completed_count', 0)

    async def on_signal(self, context):
        signal_id = context.signal.signal_id
        processed = self.state['processed_signal_ids']
        if signal_id in processed:
            return {'status': 'duplicate', 'signal_id': signal_id}

        await self.backend.execute_agent(self.node.node_id, message=self.config['message'])

        # 执行端口正常返回后才登记，异常时保持原状态交给框架处理。
        processed.append(signal_id)
        limit = self.config.get('max_history', 256)
        if len(processed) > limit:
            del processed[:len(processed) - limit]
        self.state['last_signal_id'] = signal_id
        self.state['completed_count'] += 1
        return {
            'status': 'completed',
            'signal_id': signal_id,
            'completed_count': self.state['completed_count'],
        }
