import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'

const script = readFileSync(
  new URL('../public/onlyoffice-template-link/link.js', import.meta.url),
  'utf8',
)

function createPluginHarness(selectionType = 'text', selectedText = '供试品名称', transferFails = false, tocResult) {
  if (arguments.length < 4) tocResult = true
  const calls = []
  const messages = []
  const listeners = {}
  const intervals = []
  const controls = [{ Tag: 'sample.name', InternalId: 'control-1' }]
  const Api = { GetDocument: () => ({ UpdateAllTOC: (updatePages) => {
    calls.push({ name: 'UpdateAllTOC', args: [updatePages] })
    return tocResult
  } }) }
  const fakeWindow = {
    addEventListener: (type, handler) => { listeners[type] = handler },
    setInterval: (callback) => { intervals.push(callback); return intervals.length },
    clearInterval() {},
    setTimeout: () => 1,
    clearTimeout() {},
    top: null,
    Asc: { plugin: {
      callCommand(command, _isClose, _isCalc, callback) {
        try { callback(command()) } catch { callback(false) }
      },
      executeMethod(name, args, callback) {
        calls.push({ name, args })
        const results = {
          GetAllContentControls: controls,
          GetCurrentContentControlPr: null,
          GetSelectionType: selectionType,
          GetSelectedText: selectedText,
          AddContentControl: { Tag: args[1]?.Tag, InternalId: 'control-2' },
          AddContentControlPicture: { Tag: args[0]?.Tag, InternalId: 'control-3' },
        }
        if (name === 'AddContentControl') results.GetAllContentControls = controls.concat(results.AddContentControl)
        if (name === 'AddContentControlPicture') results.GetAllContentControls = controls.concat(results.AddContentControlPicture)
        callback?.(results[name])
      },
    } },
  }
  fakeWindow.top = fakeWindow
  fakeWindow.postMessage = (message, _origin, transfer) => {
    if (transferFails && transfer) throw new Error('MessagePort transfer failed')
    messages.push(message)
  }
  class FakeMessageChannel {
    constructor() {
      this.port1 = { postMessage: (message) => messages.push(message), start() {} }
      this.port2 = { start() {} }
    }
  }
  const fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
  vm.runInNewContext(script, { window: fakeWindow, MessageChannel: FakeMessageChannel, fetch, Api })
  fakeWindow.Asc.plugin.init()
  return { calls, messages, tick: () => intervals.forEach((callback) => callback()),
    send: (data) => listeners.message({ data }) }
}

test('bridge-ready is announced without a transferable port', () => {
  const harness = createPluginHarness('text', '供试品名称', true)
  harness.tick()
  assert.ok(harness.messages.some((message) =>
    message.type === 'bridge-ready' && message.data.capabilities.includes('update-toc')))
})

test('select command immediately selects the cached content control', () => {
  const harness = createPluginHarness()
  harness.send({ source: 'report-template-host', type: 'select', tag: 'sample.name', nonce: 1 })
  assert.ok(harness.calls.some((call) =>
    call.name === 'SelectContentControl' && call.args[0] === 'control-1'))
  assert.ok(harness.calls.some((call) =>
    call.name === 'MoveCursorToContentControl' && call.args[0] === 'control-1'))
  assert.ok(harness.messages.some((message) => message.type === 'select-result'))
})

test('update-toc command updates only the table of contents and acknowledges completion', () => {
  const harness = createPluginHarness()
  harness.send({ source: 'report-template-host', type: 'update-toc', nonce: 6 })
  const updateCalls = harness.calls.filter((call) => call.name === 'UpdateAllTOC')
  assert.equal(updateCalls.length, 1)
  assert.equal(updateCalls[0].args[0], true)
  assert.ok(harness.messages.some((message) =>
    message.type === 'update-toc-result' && message.data.nonce === 6))
  assert.ok(!harness.calls.some((call) => call.name === 'UpdateAllFields'))
})

test('update-toc accepts ONLYOFFICE builds that return no command value', () => {
  const harness = createPluginHarness('text', '供试品名称', false, undefined)
  harness.send({ source: 'report-template-host', type: 'update-toc', nonce: 8 })
  assert.ok(harness.messages.some((message) =>
    message.type === 'update-toc-result' && message.data.nonce === 8))
})

test('update-toc reports an error when ONLYOFFICE does not update the document', () => {
  const harness = createPluginHarness('text', '供试品名称', false, false)
  harness.send({ source: 'report-template-host', type: 'update-toc', nonce: 7 })
  assert.ok(harness.messages.some((message) =>
    message.type === 'update-toc-error' && message.data.nonce === 7))
  assert.ok(!harness.messages.some((message) => message.type === 'update-toc-result'))
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

test('bind command creates a picture control for a selected drawing', () => {
  const harness = createPluginHarness('drawing')
  harness.send({
    source: 'report-template-host', type: 'bind', tag: 'sample.name', alias: '残差图', nonce: 3,
  })
  assert.ok(harness.calls.some((call) => call.name === 'GetSelectionType'))
  const pictureCall = harness.calls.find((call) => call.name === 'AddContentControlPicture')
  assert.ok(pictureCall)
  assert.equal(pictureCall.args[0].Tag, 'sample.name')
  assert.ok(harness.messages.some((message) =>
    message.type === 'bind-result' && message.data.objectType === 'image'))
})

test('bind command treats image selection aliases as picture controls', () => {
  const harness = createPluginHarness('image')
  harness.send({
    source: 'report-template-host', type: 'bind', tag: 'sample.name', alias: '残差图', nonce: 4,
  })
  assert.ok(!harness.calls.some((call) => call.name === 'GetSelectedText'))
  assert.ok(harness.calls.some((call) => call.name === 'AddContentControlPicture'))
  assert.ok(harness.messages.some((message) =>
    message.type === 'bind-result' && message.data.objectType === 'image'))
})

test('bind command tries a picture control when image selection has empty text', () => {
  const harness = createPluginHarness('text', '')
  harness.send({
    source: 'report-template-host', type: 'bind', tag: 'sample.name', alias: '残差图', nonce: 5,
  })
  assert.ok(harness.calls.some((call) => call.name === 'AddContentControlPicture'))
  assert.ok(harness.messages.some((message) =>
    message.type === 'bind-result' && message.data.objectType === 'image'))
})
