import { spawn } from 'node:child_process'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const appUrl = process.env.E2E_APP_URL || 'http://192.168.1.71:8010/admin/'
const session = process.env.E2E_ADMIN_SESSION
if (!session) throw new Error('E2E_ADMIN_SESSION is required')

const profile = await mkdtemp(join(tmpdir(), 'report-e2e-'))
const chrome = spawn('/usr/bin/google-chrome', [
  '--headless=new', '--no-sandbox', '--disable-gpu', '--remote-debugging-port=9223',
  `--user-data-dir=${profile}`, 'about:blank',
], { stdio: 'ignore' })

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const trace = (message) => process.stdout.write(`[e2e] ${message}\n`)
async function pageSocket() {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    try {
      const pages = await fetch('http://127.0.0.1:9223/json/list').then((value) => value.json())
      const page = pages.find((item) => item.type === 'page')
      if (page) return page.webSocketDebuggerUrl
    } catch { /* Chrome is still starting. */ }
    await delay(250)
  }
  throw new Error('Chrome DevTools did not start')
}

let nextId = 0
const pending = new Map()
const events = []
const socket = new WebSocket(await pageSocket())
socket.onmessage = ({ data }) => {
  const message = JSON.parse(data)
  if (message.id && pending.has(message.id)) {
    const { resolve, reject } = pending.get(message.id)
    pending.delete(message.id)
    if (message.error) reject(new Error(message.error.message))
    else resolve(message.result)
  } else if (message.method) events.push(message)
}
await new Promise((resolve, reject) => {
  socket.onopen = resolve
  socket.onerror = reject
})

function command(method, params = {}) {
  const id = ++nextId
  socket.send(JSON.stringify({ id, method, params }))
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }))
}

async function evaluate(expression) {
  const result = await command('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text)
  return result.result.value
}

async function waitFor(expression, timeout = 30000) {
  const started = Date.now()
  while (Date.now() - started < timeout) {
    if (await evaluate(expression)) return
    await delay(300)
  }
  throw new Error(`Timed out waiting for: ${expression}`)
}

async function click(expression) {
  const clicked = await evaluate(`(() => { const item = ${expression}; if (!item) return false; item.click(); return true })()`)
  if (!clicked) throw new Error(`Element not found: ${expression}`)
}

try {
  await command('Runtime.enable')
  await command('Network.enable')
  await command('Network.setCookie', { name: 'report_admin_session', value: session, url: appUrl })
  await command('Page.navigate', { url: appUrl })
  await waitFor(`document.body?.innerText.includes('系统概览')`)
  trace('admin ready')
  await click(`document.querySelector('button[title="报告模板与规则"]')`)
  await waitFor(`document.querySelector('.template-list button')`)
  await click(`document.querySelector('.template-list button')`)
  await waitFor(`[...document.querySelectorAll('button')].some((item) => item.innerText.includes('进入设计器'))`)
  await click(`[...document.querySelectorAll('button')].find((item) => item.innerText.includes('进入设计器'))`)
  await waitFor(`document.querySelector('#admin-onlyoffice-editor')`)
  trace('designer opened')
  await evaluate(`window.__e2eWordMessages = []; window.addEventListener('message', (event) => {
    if (event.data?.source === 'report-template-link') window.__e2eWordMessages.push(event.data)
  })`)
  await waitFor(`document.body.innerText.includes('Word 双向定位已连接')`, 45000)
  trace('plugin connected')
  if (!(await evaluate(`Boolean(document.querySelector('.field-line'))`))) {
    await click(`document.querySelector('.field-block-title')`)
  }
  await waitFor(`document.querySelector('.field-line')`)
  await click(`document.querySelector('.field-line')`)
  await waitFor(`window.__e2eWordMessages.some((item) => item.type === 'command-ack')`)
  trace('select acknowledged')
  await waitFor(`window.__e2eWordMessages.some((item) => item.type === 'select-result')`)
  trace('select completed')
  await click(`document.querySelector('.field-line button[aria-label="绑定当前 Word 位置"]')`)
  await waitFor(`window.__e2eWordMessages.filter((item) => item.type === 'command-ack').length >= 2`, 20000)
  trace('bind acknowledged')
  await waitFor(`window.__e2eWordMessages.some((item) => ['bind-result', 'bind-error'].includes(item.type))`, 20000)
  trace('bind completed')
  const result = await evaluate(`({
    state: document.querySelector('.word-state')?.innerText,
    channel: window.__e2eWordMessages.find((item) => item.type === 'bridge-ready')?.data?.channelId,
    messageTypes: window.__e2eWordMessages.map((item) => item.type),
    bindMessages: window.__e2eWordMessages.filter((item) => item.type.startsWith('bind-')),
    errors: [...document.querySelectorAll('.el-message--error')].map((item) => item.innerText),
  })`)
  process.stdout.write(`${JSON.stringify(result)}\n`)
} finally {
  socket.close()
  chrome.kill('SIGTERM')
  await Promise.race([
    new Promise((resolve) => chrome.once('exit', resolve)),
    delay(3000),
  ])
  await rm(profile, { recursive: true, force: true }).catch(() => {})
}
