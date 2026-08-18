import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'

const script = readFileSync(
  new URL('../public/onlyoffice-template-link/link.js', import.meta.url),
  'utf8',
)

function createPluginHarness() {
  const calls = []
  const messages = []
  const listeners = {}
  const controls = [{ Tag: 'sample.name', InternalId: 'control-1' }]
  const fakeWindow = {
    addEventListener: (type, handler) => { listeners[type] = handler },
    setInterval: () => 1,
    setTimeout: () => 1,
    clearTimeout() {},
    top: null,
    Asc: { plugin: {
      executeMethod(name, args, callback) {
        calls.push({ name, args })
        const results = {
          GetAllContentControls: controls,
          GetCurrentContentControlPr: null,
          GetSelectedText: '供试品名称',
          AddContentControl: { Tag: args[1]?.Tag, InternalId: 'control-2' },
        }
        callback?.(results[name])
      },
    } },
  }
  fakeWindow.top = fakeWindow
  fakeWindow.postMessage = (message) => { messages.push(message) }
  class FakeMessageChannel {
    constructor() {
      this.port1 = { postMessage: (message) => messages.push(message), start() {} }
      this.port2 = { start() {} }
    }
  }
  const fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
  vm.runInNewContext(script, { window: fakeWindow, MessageChannel: FakeMessageChannel, fetch })
  fakeWindow.Asc.plugin.init()
  return { calls, messages, send: (data) => listeners.message({ data }) }
}

test('select command immediately selects the cached content control', () => {
  const harness = createPluginHarness()
  harness.send({ source: 'report-template-host', type: 'select', tag: 'sample.name', nonce: 1 })
  assert.ok(harness.calls.some((call) =>
    call.name === 'SelectContentControl' && call.args[0] === 'control-1'))
  assert.ok(harness.calls.some((call) =>
    call.name === 'MoveCursorToContentControl' && call.args[0] === 'control-1'))
  assert.ok(harness.messages.some((message) => message.type === 'select-result'))
})

test('bind command creates a control and returns a result', () => {
  const harness = createPluginHarness()
  harness.send({
    source: 'report-template-host', type: 'bind', tag: 'sample.name', alias: '供试品名称', nonce: 2,
  })
  assert.ok(harness.calls.some((call) => call.name === 'GetSelectedText'))
  assert.ok(harness.calls.some((call) => call.name === 'AddContentControl'))
  assert.equal(harness.calls.find((call) => call.name === 'AddContentControl').args[0], 1)
  assert.ok(harness.messages.some((message) =>
    message.type === 'bind-result' && message.data.control.InternalId === 'control-2'))
})
