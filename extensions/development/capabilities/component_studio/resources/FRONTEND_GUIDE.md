# 模块前端开发规范

你可以为当前组件提供一个可选页面，由客户端在该模块的折叠区中挂载。页面负责本模块的配置编辑和只读展示。Python 业务仍通过 execute(ctx, activation) 运行，不在页面里复制核心或应用逻辑。

## 文件与清单

在 module.json 添加：

```json
"frontend": {"entry": "ui.html", "title": "元数据", "height": 320}
```

entry 必须是组件内存在的相对 .html 路径；title 为中文界面标题；height 是 160～900 的初始高度，可省略。提供自包含 HTML，CSS 和 JavaScript 写在页面内，不依赖 CDN、网络、宿主目录或其他相对资源。可以复用成熟实现，但须将需要的资源打包进页面。页面、清单、示例和测试随组件验证、发布；修改页面后重新验证。没有页面时省略 frontend。

清单顶层可选 `description`（描述）和 `preview`（书签／历史区的静态预览图）。`preview` 是自包含的 `data:image/...` 字符串，支持 PNG、JPEG、WebP、SVG，总长度不超过 350000 字符；例如 `"preview":"data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20viewBox='0%200%2060%2040'%3E%3Ccircle%20cx='30'%20cy='20'%20r='12'%20fill='%238bd9bf'/%3E%3C/svg%3E"`。位图使用 Base64，SVG 使用 URL 编码；不使用本地绝对路径或外部图片网址。它只是可选展示资料，不执行模块或页面代码；无图、图片失效时显示模块名称。清单跟随正常验证、发布流程，无需改变执行接口。

使用完整 HTML 文档，包含 head 和 body，设置 lang="zh-CN"、UTF-8 及视口。界面采用深色背景，适应约 260 像素起的窄面板；表单控件有中文标签。集合编辑提供添加、删除、名称和值的输入，按需要提供类型选择，正确保留数字、布尔、对象和空值。不要用弹窗代替页面上的常规输入。

## 客户端注入的接口

客户端在页面脚本之前提供 window.NexarborModule。不要自己实现或覆盖它。

```javascript
const host = window.NexarborModule;
let current;
host.onContext(context => {
  current = context;
  // 根据 context.config 绘制当前配置；更新时不要覆盖正在输入的临时草稿。
});

async function save(nextConfig) {
  try {
    await host.setConfig(nextConfig);
    // 显示“已写入网络草稿，应用网络后生效”。
  } catch (error) {
    // 在页面内显示 error.message，保留用户输入以便修正。
  }
}
```

onContext(callback) 订阅首次上下文与后续更新，返回取消订阅函数。getContext() 返回当前上下文副本，尚未收到时为 null。上下文包含：

- module：模块 ID；node：所在节点的 id/name/type，工作室预览时可为 null。
- config：本模块配置；state：本模块状态的只读副本，预览时可以为空。
- configSchema：配置的 JSON Schema；readOnly：是否只读；instance：当前页面实例标识，交给接口内部使用。

setConfig(nextConfig) 返回 Promise，提交的是完整配置对象。保留未编辑的其他配置字段；客户端校验 Schema 并且只修改当前模块的配置，失败时 Promise 被拒绝。挂载实例的修改进入网络草稿，仍需点击客户端的“应用网络”才影响运行实例。node 为 null 时显示“待装配配置已更新”，由外层 Save 保存为配置书签；源码页面预览只修改预览配置，不代替保存 example.json。

resize(height) 请求页面高度，客户端限制为 160～900 像素。建议在内容变化后调用；不要无限重试。readOnly 为 true 时禁用修改控件。

## 边界与测试

页面通过受限 iframe 运行，不能读取父页面 DOM、宿主令牌、凭据、本地文件或任意后端 RPC。不能更改节点 ID、网络连接、访问频道、强度或其他模块。不要使用 fetch、终端、弹窗、下载、外部脚本或自行打开其他窗口；当前仅提供上述配置接口。

页面隐藏或关闭后可能重新挂载，不把界面内存当作业务状态。依赖 config 的更新重新渲染；不要在 onContext 中无条件 setConfig，避免循环。用 textContent 或等价安全文本绑定展示用户输入，不拼接到 innerHTML。

说明添加、修改、删除、类型保留、非法值提示和折叠重开的验收步骤。宿主通用检查验证入口与文件，页面交互需要客户端实测；不要将“Python 测试通过”说成“页面交互已测试”。
