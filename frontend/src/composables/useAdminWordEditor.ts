import { nextTick, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminApi } from '../admin-api'
import { adminErrorText } from '../admin/designer-formatters'
import { loadOnlyOfficeApi } from './onlyofficeApiLoader'

type Connector = {
  executeMethod?: (name: string, args: unknown[], callback?: (result: unknown) => void) => void
  disconnect?: () => void
}
type Editor = { destroyEditor?: () => void; createConnector?: () => Connector }
export type WordControl = {
  Tag?: string; tag?: string; InternalId?: string; internalId?: string; Id?: string; id?: string
}

declare global {
  interface Window {
    DocsAPI?: { DocEditor: new (elementId: string, config: Record<string, unknown>) => Editor }
    __reportTemplateLinkCommand?: {
      type: 'select'; tag?: string; id?: string; index?: number; nonce: number
    }
  }
}

export function controlTag(control?: WordControl | null) {
  return control?.Tag || control?.tag || ''
}
export function controlId(control?: WordControl | null) {
  return control?.InternalId || control?.internalId || control?.Id || control?.id || ''
}

export function useAdminWordEditor(onTag: (tag: string) => void) {
  const ready = ref(false)
  const loading = ref(false)
  const error = ref('')
  const linkState = ref<'CONNECTING' | 'READY' | 'LIMITED'>('CONNECTING')
  const controls = ref<WordControl[]>([])
  const pluginReady = ref(false)
  const pendingTag = ref<string>()
  const pendingBinds = new Map<number, {
    resolve: (value: { control: WordControl; selectedText: string; existing: boolean }) => void
    reject: (reason: Error) => void
    timer: number
    acknowledged: boolean
  }>()
  const pendingUnbinds = new Map<number, {
    resolve: () => void; reject: (reason: Error) => void; timer: number; acknowledged: boolean
  }>()
  const pendingSelects = new Map<number, number>()
  let editor: Editor | undefined
  let connector: Connector | undefined
  let pluginWindow: Window | null = null
  let pluginPort: MessagePort | null = null
  let pluginCompatible = false
  let pluginChannel = ''
  let selectionTimer: number | undefined

  function hasConnector() { return Boolean(connector?.executeMethod) }

  function sendPluginCommand(command: Record<string, unknown>) {
    const message = { source: 'report-template-host', ...command }
    console.info('[WordBridge]', { stage: 'host-send', channel: pluginChannel,
      hasPort: Boolean(pluginPort), hasWindow: Boolean(pluginWindow), ...command })
    if (pluginPort) pluginPort.postMessage(message)
    pluginWindow?.postMessage(message, '*')
    if (pluginChannel) {
      void fetch(`/api/v1/onlyoffice/plugin-bridge/${encodeURIComponent(pluginChannel)}`, {
        method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(message),
      }).then((response) => console.info('[WordBridge]', { stage: 'relay-submit',
        channel: pluginChannel, nonce: command.nonce, status: response.status }))
        .catch((value) => console.error('[WordBridge] 命令中继失败', value))
    }
    return Boolean(pluginPort || pluginWindow || pluginChannel)
  }

  async function bridgeStages(nonce: number) {
    if (!pluginChannel) return []
    try {
      const response = await fetch(
        `/api/v1/onlyoffice/plugin-bridge/${encodeURIComponent(pluginChannel)}/trace`,
        { credentials: 'include', cache: 'no-store' },
      )
      if (!response.ok) return []
      const events = await response.json() as Array<{ nonce?: number; stage?: string }>
      return events.filter((event) => event.nonce === nonce).map((event) => String(event.stage || ''))
    } catch (value) {
      console.error('[WordBridge] 读取通信追踪失败', value)
      return []
    }
  }

  async function commandTimeoutMessage(nonce: number, action: string, acknowledged: boolean) {
    const stages = await bridgeStages(nonce)
    console.error('[WordBridge]', { stage: `${action}-timeout`, channel: pluginChannel,
      nonce, acknowledged, traceStages: stages })
    if (stages.includes(`plugin-send-${action}-error`) || stages.includes(`plugin-send-${action}-result`))
      return `Word 已完成${action === 'bind' ? '绑定' : '定位'}处理，但页面未收到回执，请重新打开设计器`
    if (stages.includes('plugin-command-received'))
      return `Word 插件已收到${action === 'bind' ? '绑定' : '定位'}命令，但执行未完成`
    if (stages.includes('host-submit'))
      return `定位中继已收到命令，但 Word 插件未能轮询，请重新打开设计器`
    return acknowledged ? 'Word 已收到命令，但执行未完成' : 'Word 插件连接已失效，请重新打开设计器'
  }

  function exec(name: string, args: unknown[] = [], timeoutMs = 6000) {
    return new Promise<unknown>((resolve, reject) => {
      if (!connector?.executeMethod) return resolve(undefined)
      const timer = window.setTimeout(
        () => reject(new Error(`Word 操作 ${name} 响应超时`)), timeoutMs,
      )
      try {
        connector.executeMethod(name, args, (result) => {
          window.clearTimeout(timer)
          resolve(result)
        })
      } catch (value) {
        window.clearTimeout(timer)
        reject(value)
      }
    })
  }

  async function refreshControls() {
    const result = await exec('GetAllContentControls')
    controls.value = Array.isArray(result) ? result as WordControl[] : []
    linkState.value = controls.value.length ? 'READY' : 'LIMITED'
  }

  async function connect() {
    connector?.disconnect?.()
    connector = editor?.createConnector?.()
    if (!connector?.executeMethod) {
      linkState.value = 'LIMITED'
      return
    }
    await refreshControls()
    if (selectionTimer) window.clearInterval(selectionTimer)
    selectionTimer = window.setInterval(async () => {
      try {
        const current = await exec('GetCurrentContentControlPr') as WordControl | undefined
        const tag = controlTag(current)
        if (tag) onTag(tag)
      } catch { /* A later poll can recover after the editor is responsive again. */ }
    }, 700)
  }

  function settleBind(type: string, data: unknown) {
    const result = data as {
      nonce: number; message?: string; control?: WordControl; selectedText?: string; existing?: boolean
    }
    const pending = pendingBinds.get(result.nonce)
    if (!pending) return
    window.clearTimeout(pending.timer)
    pendingBinds.delete(result.nonce)
    if (type === 'bind-error') pending.reject(new Error(result.message || 'Word 绑定失败'))
    else pending.resolve({
      control: result.control || {}, selectedText: result.selectedText || '', existing: Boolean(result.existing),
    })
  }

  function settleUnbind(type: string, data: unknown) {
    const result = data as { nonce: number; message?: string }
    const pending = pendingUnbinds.get(result.nonce)
    if (!pending) return
    window.clearTimeout(pending.timer)
    pendingUnbinds.delete(result.nonce)
    if (type === 'unbind-error') pending.reject(new Error(result.message || '解除 Word 绑定失败'))
    else pending.resolve()
  }

  function handlePluginMessage(message: { source?: string; type?: string; data?: unknown }, source?: MessageEventSource | null) {
    if (message?.source !== 'report-template-link') return
    console.info('[WordBridge]', { stage: 'host-receive', channel: pluginChannel,
      messageType: message.type, data: message.data })
    if (message.type === 'controls' && Array.isArray(message.data)) {
      if (source) pluginWindow = source as Window
      pluginReady.value = pluginCompatible || Boolean(pluginWindow)
      controls.value = message.data as WordControl[]
      linkState.value = pluginReady.value ? 'READY' : 'LIMITED'
      ready.value = true
      if (editor?.createConnector && !connector?.executeMethod) void connect()
    } else if (message.type === 'command-ack' && message.data) {
      const nonce = Number((message.data as { nonce?: number }).nonce || 0)
      const pending = pendingBinds.get(nonce) || pendingUnbinds.get(nonce)
      if (pending) pending.acknowledged = true
    } else if (message.type === 'selection' && message.data) {
      const tag = controlTag(message.data as WordControl)
      if (tag) onTag(tag)
    } else if (message.type === 'bind-result' || message.type === 'bind-error') {
      if (message.data) settleBind(message.type, message.data)
    } else if (message.type === 'select-result' || message.type === 'select-error') {
      const result = message.data as { nonce?: number; message?: string } | undefined
      const nonce = Number(result?.nonce || 0)
      const timer = pendingSelects.get(nonce)
      if (timer) window.clearTimeout(timer)
      pendingSelects.delete(nonce)
      if (message.type === 'select-error') ElMessage.warning(result?.message || 'Word 中没有找到该字段')
    } else if (message.type === 'unbind-result' || message.type === 'unbind-error') {
      if (message.data) settleUnbind(message.type, message.data)
    }
  }

  function handleMessage(event: MessageEvent) {
    const message = event.data as { source?: string; type?: string; data?: unknown }
    if (message?.source !== 'report-template-link') return
    if (message.type === 'bridge-ready') {
      const bridge = message.data as {
        protocolVersion?: number; capabilities?: string[]; channelId?: string
      } | undefined
      pluginCompatible = Number(bridge?.protocolVersion || 0) >= 3 &&
        ['bind', 'select', 'unbind'].every((item) => bridge?.capabilities?.includes(item))
      pluginPort?.close()
      pluginChannel = String(bridge?.channelId || '')
      pluginPort = event.ports[0] || null
      pluginWindow = event.source as Window | null
      console.info('[WordBridge]', { stage: 'bridge-ready', channel: pluginChannel,
        compatible: pluginCompatible, hasPort: Boolean(pluginPort), hasWindow: Boolean(pluginWindow), bridge })
      if (pluginPort) {
        pluginPort.onmessage = (portEvent) => handlePluginMessage(portEvent.data)
        pluginPort.start()
      }
      pluginReady.value = false
      linkState.value = pluginCompatible ? 'CONNECTING' : 'LIMITED'
      return
    }
    handlePluginMessage(message, event.source)
  }

  function requestBind(alias: string, tag: string, oldInternalId: string) {
    const nonce = Date.now()
    return new Promise<{ control: WordControl; selectedText: string; existing: boolean }>((resolve, reject) => {
      const timer = window.setTimeout(async () => {
        const pending = pendingBinds.get(nonce)
        pendingBinds.delete(nonce)
        reject(new Error(await commandTimeoutMessage(nonce, 'bind', Boolean(pending?.acknowledged))))
      }, 12000)
      pendingBinds.set(nonce, { resolve, reject, timer, acknowledged: false })
      const command = { type: 'bind', nonce, tag, alias, oldInternalId }
      if (sendPluginCommand(command)) return
      window.clearTimeout(timer)
      pendingBinds.delete(nonce)
      reject(new Error('Word 插件尚未建立双向连接'))
    })
  }

  function requestUnbind(id = '') {
    const nonce = Date.now()
    return new Promise<void>((resolve, reject) => {
      const timer = window.setTimeout(() => {
        const pending = pendingUnbinds.get(nonce)
        pendingUnbinds.delete(nonce)
        reject(new Error(pending?.acknowledged
          ? 'Word 已收到解除命令，但执行未完成'
          : 'Word 插件未收到解除命令，请重新加载编辑器'))
      }, 12000)
      pendingUnbinds.set(nonce, { resolve, reject, timer, acknowledged: false })
      const command = { type: 'unbind', nonce, id }
      if (sendPluginCommand(command)) return
      window.clearTimeout(timer)
      pendingUnbinds.delete(nonce)
      reject(new Error('Word 插件尚未建立双向连接'))
    })
  }

  async function locate(tag?: string) {
    if (!tag) return
    const id = controlId(controls.value.find((item) => controlTag(item) === tag))
    const command = { type: 'select' as const, tag, id, nonce: Date.now() }
    window.__reportTemplateLinkCommand = command
    const sentToPlugin = sendPluginCommand(command)
    if (sentToPlugin) {
      const timer = window.setTimeout(async () => {
        pendingSelects.delete(command.nonce)
        ElMessage.warning(await commandTimeoutMessage(command.nonce, 'select', false))
      }, 5000)
      pendingSelects.set(command.nonce, timer)
      return
    }
    if (ready.value && hasConnector() && id) {
      await exec('SelectContentControl', [id])
      await exec('MoveCursorToContentControl', [id, false])
      return
    }
    if (!ready.value) {
      pendingTag.value = tag
      return
    }
    pendingTag.value = undefined
  }

  async function open() {
    loading.value = true
    error.value = ''
    ready.value = false
    linkState.value = 'CONNECTING'
    try {
      close()
      loading.value = true
      linkState.value = 'CONNECTING'
      const bootstrap = await adminApi.onlyOfficeConfig()
      await loadOnlyOfficeApi(bootstrap.documentServerUrl)
      await nextTick()
      if (!window.DocsAPI) throw new Error('ONLYOFFICE 编辑器 API 不可用')
      bootstrap.config.events = {
        onDocumentReady: async () => {
          ready.value = true
          await connect()
          if (pendingTag.value) await locate(pendingTag.value)
        },
        onError: (event: unknown) => { error.value = `模板编辑器发生错误：${JSON.stringify(event)}` },
      }
      editor = new window.DocsAPI.DocEditor('admin-onlyoffice-editor', bootstrap.config)
    } catch (value) {
      error.value = adminErrorText(value)
    } finally {
      loading.value = false
    }
  }

  function close() {
    if (selectionTimer) window.clearInterval(selectionTimer)
    connector?.disconnect?.()
    pluginPort?.close()
    editor?.destroyEditor?.()
    connector = undefined
    pluginPort = null
    pluginWindow = null
    pluginReady.value = false
    pluginCompatible = false
    pluginChannel = ''
    pendingBinds.forEach((pending) => {
      window.clearTimeout(pending.timer)
      pending.reject(new Error('Word 编辑器已关闭，绑定操作已取消'))
    })
    pendingUnbinds.forEach((pending) => {
      window.clearTimeout(pending.timer)
      pending.reject(new Error('Word 编辑器已关闭，解除操作已取消'))
    })
    pendingBinds.clear()
    pendingUnbinds.clear()
    pendingSelects.forEach((timer) => window.clearTimeout(timer))
    pendingSelects.clear()
    editor = undefined
    ready.value = false
  }

  window.addEventListener('message', handleMessage)
  onUnmounted(() => {
    window.removeEventListener('message', handleMessage)
    close()
  })

  return {
    ready, loading, error, linkState, controls, pluginReady, hasConnector,
    exec, refreshControls, requestBind, requestUnbind, locate, open, close,
  }
}
