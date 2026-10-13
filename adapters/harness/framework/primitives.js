import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createUserMessage} from '@deepseek-ai/dsh-llm';
const here = path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const compactFeedback = report => ({
  node_id: report.actor,
  error: report.message
});
const object = (properties = {}, required = []) => ({
  type: 'object',
  properties,
  required,
  additionalProperties: false
});
const str = {
    type: 'string'
  },
  number = {
    type: 'number',
    minimum: 0
  };
const readRequest = {
  type: 'object',
  properties: {
    method: {
      type: 'string',
      enum: ['key', 'filter', 'semantic']
    },
    key: str,
    filters: {
      type: 'object'
    },
    query: str,
    top_k: {
      type: 'integer',
      minimum: 1
    }
  },
  required: ['method'],
  additionalProperties: false,
  description: '文本节点读取必须使用 {"method":"key","key":"content"}。filter需filters，semantic需query；不要混用字段。'
};
const user = text => createUserMessage({
  source: {
    kind: 'user'
  },
  content: [{
    type: 'text',
    text
  }]
});
const checked = value => {
  if (value?.status && value.status !== 'ok') throw new Error(JSON.stringify(value));
  return value;
};
export {here,compactFeedback,object,str,number,readRequest,user,checked};
