const API_SCRIPT_SELECTOR = 'script[data-onlyoffice-api]'
const LOAD_TIMEOUT_MS = 12000

type DocsWindow = Window & { DocsAPI?: unknown }

function docsApiAvailable() {
  return Boolean((window as DocsWindow).DocsAPI)
}

function waitForScript(script: HTMLScriptElement, url: string) {
  return new Promise<void>((resolve, reject) => {
    const cleanup = () => {
      window.clearTimeout(timer)
      script.removeEventListener('load', loaded)
      script.removeEventListener('error', failed)
    }
    const fail = (message: string) => {
      cleanup()
      script.dataset.loadState = 'failed'
      script.remove()
      reject(new Error(`${message}：${url}`))
    }
    const loaded = () => {
      if (!docsApiAvailable()) return fail('ONLYOFFICE 编辑器脚本无效')
      cleanup()
      script.dataset.loadState = 'loaded'
      resolve()
    }
    const failed = () => fail('ONLYOFFICE 编辑器脚本加载失败')
    const timer = window.setTimeout(() => fail('ONLYOFFICE 编辑器脚本加载超时'), LOAD_TIMEOUT_MS)
    script.addEventListener('load', loaded, { once: true })
    script.addEventListener('error', failed, { once: true })
  })
}

export function loadOnlyOfficeApi(serverUrl: string) {
  if (docsApiAvailable()) return Promise.resolve()
  const url = `${serverUrl.replace(/\/$/, '')}/web-apps/apps/api/documents/api.js`
  const existing = document.querySelector<HTMLScriptElement>(API_SCRIPT_SELECTOR)
  if (existing?.dataset.loadState === 'loading') return waitForScript(existing, url)
  existing?.remove()
  const script = document.createElement('script')
  script.src = url
  script.dataset.onlyofficeApi = 'true'
  script.dataset.loadState = 'loading'
  const loading = waitForScript(script, url)
  document.head.appendChild(script)
  return loading
}
