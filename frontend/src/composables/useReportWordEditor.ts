import { nextTick, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { forceSaveOnlyOffice, getOnlyOfficeConfig } from '../api'
import { loadOnlyOfficeApi } from './onlyofficeApiLoader'

type WordConnector = {
  executeMethod?: (name: string, args: unknown[], callback?: (result: unknown) => void) => void
  disconnect?: () => void
}
type WordEditor = { destroyEditor?: () => void; createConnector?: () => WordConnector }
type WordControl = {
  Tag?: string; tag?: string; InternalId?: string; internalId?: string; Id?: string; id?: string
}

declare global {
  interface Window {
    DocsAPI?: { DocEditor: new (elementId: string, config: Record<string, unknown>) => WordEditor }
    __reportTemplateLinkCommand?: {
      type: 'select'; tag?: string; id?: string; index?: number; nonce: number
    }
  }
}

interface WordEditorOptions {
  reportId: () => string | undefined
  editorContainer: () => HTMLElement | null
  requiresFieldRefresh: () => boolean
  onDocumentSaved: (reportId: string) => void | Promise<void>
  onRequestClose: () => void | Promise<void>
}

export function useReportWordEditor(options: WordEditorOptions) {
  const loading = ref(false)
  const error = ref('')
  const linkStatus = ref<'WAITING' | 'CONNECTOR' | 'PLUGIN'>('WAITING')
  let editor: WordEditor | undefined
  let connector: WordConnector | undefined
  let wordReady = false
  let pluginReady = false
  let pluginWindow: Window | null = null
  let pluginPort: MessagePort | null = null
  let pluginCompatible = false
  let pluginChannel = ''
  let tocCapability = false
  let pendingToc: { nonce: number; resolve: () => void; reject: (error: Error) => void } | undefined
  let preparingFields = false
  let pendingLocation: { tag: string; index: number } | undefined
  let locationTimer: number | undefined

  function errorText(value: unknown) {
    return value instanceof Error ? value.message : 'ONLYOFFICE 加载失败'
  }

  function execWord(name: string, args: unknown[] = []) {
    return new Promise<unknown>((resolve) => {
      if (!connector?.executeMethod) return resolve(undefined)
      try { connector.executeMethod(name, args, resolve) } catch { resolve(undefined) }
    })
  }

  function controlTag(control: WordControl) { return control.Tag || control.tag || '' }
  function controlId(control: WordControl) {
    return control.InternalId || control.internalId || control.Id || control.id || ''
  }

  async function locate(tag: string, index = 0) {
    const command = { type: 'select' as const, tag, index, nonce: Date.now() }
    window.__reportTemplateLinkCommand = command
    if (pluginReady && (pluginPort || pluginWindow)) {
      const message = { source: 'report-template-host', ...command }
      console.info('[WordBridge] 通过插件定位字段', { tag, index, nonce: command.nonce })
      if (pluginPort) pluginPort.postMessage(message)
      pluginWindow?.postMessage(message, '*')
      if (pluginChannel) {
        void fetch(`/api/v1/onlyoffice/plugin-bridge/${encodeURIComponent(pluginChannel)}`, {
          method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(message),
        }).catch((value) => console.error('[WordBridge] 命令中继失败', value))
      }
      if (locationTimer) window.clearTimeout(locationTimer)
      locationTimer = window.setTimeout(() => {
        ElMessage.warning('定位命令已发送，但 Word 插件未返回结果，请重新加载编辑器')
      }, 3000)
      return
    }
    if (wordReady && connector?.executeMethod) {
      console.info('[WordBridge] 通过 Connector 定位字段', { tag, index })
      const result = await execWord('GetAllContentControls')
      const controls = Array.isArray(result) ? result as WordControl[] : []
      const matches = controls.filter((control) => controlTag(control) === tag)
      const id = controlId(matches[Math.min(index, Math.max(0, matches.length - 1))] || {})
      if (!id) return ElMessage.warning('Word 中没有找到该字段的绑定位置')
      await execWord('SelectContentControl', [id])
      await execWord('MoveCursorToContentControl', [id, false])
      return
    }
    if (!wordReady || !connector?.executeMethod) {
      pendingLocation = { tag, index }
      return
    }
  }

  function handleMessage(event: MessageEvent) {
    const message = event.data as { source?: string; type?: string; data?: unknown }
    if (message?.source !== 'report-template-link') return
    if (message.type === 'bridge-ready') {
      const bridge = message.data as {
        protocolVersion?: number; capabilities?: string[]; channelId?: string
      } | undefined
      if (pluginReady && pluginChannel === bridge?.channelId) return
      pluginCompatible = Number(bridge?.protocolVersion || 0) >= 3 &&
        Boolean(bridge?.capabilities?.includes('select'))
      tocCapability = Boolean(bridge?.capabilities?.includes('update-toc'))
      pluginPort?.close()
      pluginChannel = String(bridge?.channelId || '')
      pluginPort = event.ports[0] || null
      pluginWindow = event.source as Window | null
      if (pluginPort) {
        pluginPort.onmessage = (portEvent) => handleMessage(portEvent as MessageEvent)
        pluginPort.start()
      }
      pluginReady = pluginCompatible
      if (pluginReady) linkStatus.value = 'PLUGIN'
      return
    }
    if (message.type === 'select-result') {
      if (locationTimer) window.clearTimeout(locationTimer)
      locationTimer = undefined
      return
    }
    if (message.type === 'command-ack') {
      const data = message.data as { nonce?: number; commandType?: string } | undefined
      if (data?.commandType === 'update-toc' && data.nonce === pendingToc?.nonce) {
        console.info('[ONLYOFFICE] 插件已接收目录更新命令')
      }
      return
    }
    if ((message.type === 'update-toc-result' || message.type === 'update-toc-error') && pendingToc) {
      const data = message.data as { nonce?: number; message?: string } | undefined
      if (data?.nonce !== pendingToc.nonce) return
      const pending = pendingToc
      pendingToc = undefined
      console.info('[ONLYOFFICE] 目录更新插件返回', message.type)
      if (message.type === 'update-toc-error') pending.reject(new Error(data.message || 'ONLYOFFICE 更新目录失败'))
      else pending.resolve()
      return
    }
    if (message.type === 'select-error') {
      if (locationTimer) window.clearTimeout(locationTimer)
      locationTimer = undefined
      const data = message.data as { message?: string } | undefined
      ElMessage.warning(data?.message || 'Word 中没有找到该字段的绑定位置')
      return
    }
    if (message.type !== 'controls') return
    if (event.source) pluginWindow = event.source as Window
    pluginReady = pluginCompatible || Boolean(pluginWindow)
    linkStatus.value = 'PLUGIN'
    wordReady = true
    if (!connector?.executeMethod) connector = editor?.createConnector?.()
    if (pendingLocation) {
      const location = pendingLocation
      pendingLocation = undefined
      void locate(location.tag, location.index)
    }
  }

  function close() {
    connector?.disconnect?.()
    connector = undefined
    wordReady = false
    pluginReady = false
    pluginCompatible = false
    tocCapability = false
    pendingToc?.reject(new Error('ONLYOFFICE 编辑器已关闭，目录更新已取消'))
    pendingToc = undefined
    pluginChannel = ''
    pluginWindow = null
    pluginPort?.close()
    pluginPort = null
    if (locationTimer) window.clearTimeout(locationTimer)
    locationTimer = undefined
    editor?.destroyEditor?.()
    editor = undefined
    options.editorContainer()?.replaceChildren()
  }

  async function loadEditor(reportId: string, prepare: boolean) {
    const bootstrap = await getOnlyOfficeConfig(reportId, prepare)
    const config = bootstrap.config as Record<string, unknown> & { events?: Record<string, unknown> }
    await loadOnlyOfficeApi(bootstrap.documentServerUrl)
    await nextTick()
    if (!window.DocsAPI) throw new Error('ONLYOFFICE 编辑器 API 不可用')
    const container = options.editorContainer()
    if (!container) throw new Error('ONLYOFFICE 编辑器容器不存在')
    const host = document.createElement('div')
    host.id = 'onlyoffice-editor'
    host.style.width = '100%'
    host.style.height = '100%'
    container.replaceChildren(host)
    await new Promise<void>((resolve, reject) => {
      const timer = window.setTimeout(() => reject(new Error('ONLYOFFICE 文档加载超时，请重试')), 60000)
      const ready = () => { window.clearTimeout(timer); resolve() }
      const fail = () => { window.clearTimeout(timer); reject(new Error('ONLYOFFICE 文档加载失败，请重试')) }
      config.events = {
        ...(config.events || {}),
        onDocumentReady: () => {
          wordReady = true
          connector = editor?.createConnector?.()
          if (connector?.executeMethod) linkStatus.value = 'CONNECTOR'
          if (pendingLocation) {
            const location = pendingLocation
            pendingLocation = undefined
            void locate(location.tag, location.index)
          }
          ready()
        },
        onError: fail,
        onDocumentStateChange: (event: { data?: boolean }) => {
          if (event.data !== false || preparingFields) return
          window.setTimeout(() => void options.onDocumentSaved(reportId), 1500)
        },
        onRequestClose: () => void options.onRequestClose(),
      }
      try { editor = new window.DocsAPI!.DocEditor('onlyoffice-editor', config) }
      catch (value) { window.clearTimeout(timer); reject(value) }
    })
  }

  async function open() {
    const reportId = options.reportId()
    if (!reportId) return
    loading.value = true
    error.value = ''
    close()
    linkStatus.value = 'WAITING'
    try {
      const prepare = options.requiresFieldRefresh()
      preparingFields = prepare
      await loadEditor(reportId, prepare)
      if (prepare) {
        try {
          await updateFields()
          console.info('[ONLYOFFICE] 目录更新完成，继续使用当前编辑器实例')
        } finally {
          preparingFields = false
        }
      }
    } catch (value) {
      preparingFields = false
      close()
      const responseDetail = (value as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      if (typeof responseDetail === 'string' && responseDetail.trim()) {
        error.value = responseDetail
      } else if (responseDetail && typeof responseDetail === 'object' && 'message' in responseDetail) {
        error.value = String((responseDetail as { message?: unknown }).message || '报告文档准备失败')
      } else {
        error.value = errorText(value)
      }
    } finally {
      loading.value = false
    }
  }

  async function save() {
    const reportId = options.reportId()
    if (!reportId || !editor) return
    await forceSaveOnlyOffice(reportId)
  }

  async function updateFields() {
    if (!wordReady) {
      throw new Error('ONLYOFFICE 编辑器尚未就绪，无法更新目录')
    }
    console.info('[ONLYOFFICE] 请求更新目录')
    const deadline = Date.now() + 10000
    while (!tocCapability && Date.now() < deadline) {
      await new Promise<void>((resolve) => window.setTimeout(resolve, 100))
    }
    if (!tocCapability || (!pluginPort && !pluginWindow)) {
      throw new Error('ONLYOFFICE 目录更新插件未就绪，请重新打开报告')
    }
    const nonce = Date.now()
    const completion = new Promise<void>((resolve, reject) => {
      const timer = window.setTimeout(() => {
        pendingToc = undefined
        reject(new Error('ONLYOFFICE 更新目录超时，请重试'))
      }, 30000)
      pendingToc = {
        nonce,
        resolve: () => { window.clearTimeout(timer); resolve() },
        reject: (error) => { window.clearTimeout(timer); reject(error) },
      }
      const command = { source: 'report-template-host', type: 'update-toc', nonce }
      if (pluginPort) pluginPort.postMessage(command)
      else pluginWindow?.postMessage(command, '*')
    })
    const relay = pluginChannel
      ? fetch(`/api/v1/onlyoffice/plugin-bridge/${encodeURIComponent(pluginChannel)}`, {
          method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ source: 'report-template-host', type: 'update-toc', nonce }),
        }).then((response) => {
          if (!response.ok) throw new Error('ONLYOFFICE 目录命令中继失败，请重试')
        })
      : Promise.resolve()
    await Promise.all([completion, relay])
  }

  window.addEventListener('message', handleMessage)
  onUnmounted(() => {
    window.removeEventListener('message', handleMessage)
    if (locationTimer) window.clearTimeout(locationTimer)
    close()
  })

  return { loading, error, linkStatus, locate, open, close, save, updateFields }
}
