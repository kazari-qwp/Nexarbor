// Harness stores the provider termination reason in assistant replay metadata.
export function assertCompleteOutput(messages) {
  for (const message of messages) {
    if (message.role !== 'assistant') continue;
    const response=message.source?.replayState?.response;
    const reason=response?.stopReason ?? response?.finishReason ?? response?.finish_reason ?? message.stopReason ?? message.finishReason ?? message.finish_reason;
    if (['length','max_tokens','max_output_tokens'].includes(reason)) {
      const error=new Error('MODEL_OUTPUT_TRUNCATED: 模型输出达到上限；工具调用或回复可能未完成。任务未标记成功。请检查已执行结果后继续，避免重复执行。');
      error.code='MODEL_OUTPUT_TRUNCATED';throw error;
    }
  }
}
