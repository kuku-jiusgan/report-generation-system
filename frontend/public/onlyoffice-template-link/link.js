(function (window) {
  'use strict'
  var controls = []
  var lastTag = ''
  var lastCommand = 0
  var hostPort = null
  var serviceUrl = ''
  var lastServerCommand = 0
  var channelId = 'word-' + Date.now() + '-' + Math.random().toString(36).slice(2)

  function send(type, data) {
    var message = { source: 'report-template-link', type: type, data: data || null }
    try {
      if (hostPort) hostPort.postMessage(message)
    } catch (_) { /* Window messaging remains available below. */ }
    try {
      window.top.postMessage(message, '*')
    } catch (_) { /* The host can still use one-way rule-to-Word navigation. */ }
    trace('plugin-send-' + type, data || {})
  }

  function trace(stage, data) {
    if (!serviceUrl) return
    var payload = data || {}
    fetch(serviceUrl + '/' + encodeURIComponent(channelId) + '/trace', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        stage: stage, nonce: Number(payload.nonce || 0),
        type: String(payload.commandType || payload.type || '')
      })
    }).catch(function () {})
  }

  function readControls() {
    window.Asc.plugin.executeMethod('GetAllContentControls', [], function (result) {
      controls = Array.isArray(result) ? result : []
      send('controls', controls)
    })
  }

  function readSelection() {
    window.Asc.plugin.executeMethod('GetCurrentContentControlPr', [], function (result) {
      var tag = result && (result.Tag || result.tag) || ''
      if (tag && tag !== lastTag) {
        lastTag = tag
        send('selection', result)
      }
    })
  }

  function processHostCommand() {
    var command
    try { command = window.top.__reportTemplateLinkCommand } catch (_) { return }
    if (!command || command.nonce === lastCommand || command.type !== 'select') return
    lastCommand = command.nonce
    var matches = controls.filter(function (item) {
      return (command.id && (item.InternalId === command.id || item.Id === command.id)) ||
        (command.tag && (item.Tag === command.tag || item.tag === command.tag))
    })
    var control = matches[Math.min(Number(command.index || 0), Math.max(0, matches.length - 1))]
    var id = control && (control.InternalId || control.Id)
    selectControl(command, id)
  }

  function itemTag(item) {
    return item && (item.Tag || item.tag) || ''
  }

  function itemId(item) {
    return item && (item.InternalId || item.internalId || item.Id || item.id) || ''
  }

  function resolveControl(command, knownId) {
    var matches = command.tag
      ? controls.filter(function (item) { return itemTag(item) === command.tag })
      : []
    if (!matches.length && knownId) {
      matches = controls.filter(function (item) { return String(itemId(item)) === String(knownId) })
    }
    return matches[Math.min(Number(command.index || 0), Math.max(0, matches.length - 1))]
  }

  function selectControl(command, knownId) {
    var control = resolveControl(command, knownId)
    var id = itemId(control)
    if (!id) {
      send('select-error', { nonce: command.nonce, tag: command.tag, message: 'Word 中没有找到该字段的绑定位置' })
      return
    }
    trace('plugin-select-control', command)
    window.Asc.plugin.executeMethod('SelectContentControl', [id], function () {
      trace('plugin-select-complete', command)
      window.Asc.plugin.executeMethod('MoveCursorToContentControl', [id, false], function () {
        trace('plugin-move-complete', command)
        send('select-result', { nonce: command.nonce, tag: command.tag, id: id })
      })
    })
  }

  function receiveHostCommand(command) {
    if (!command || command.source !== 'report-template-host') return
    if (command.nonce === lastCommand) return
    lastCommand = command.nonce
    trace('plugin-command-received', command)
    send('command-ack', { nonce: command.nonce, commandType: command.type })
    if (command.type === 'select') selectControl(command, command.id)
    else if (command.type === 'bind') bindSelection(command)
    else if (command.type === 'unbind') unbindSelection(command)
    else if (command.type === 'detect-table') detectTable(command)
  }

  function detectTable(command) {
    window.Asc.plugin.executeMethod('GetCurrentTableIndex', [], function (result) {
      var index = typeof result === 'number' ? result : Number(result && result.index)
      send(index > 0 ? 'table-detect-result' : 'table-detect-error', { nonce: command.nonce, index: index })
    })
  }

  window.addEventListener('message', function (event) {
    receiveHostCommand(event.data)
  })

  function connectHost() {
    try {
      var channel = new MessageChannel()
      hostPort = channel.port1
      hostPort.onmessage = function (event) { receiveHostCommand(event.data) }
      hostPort.start()
      window.top.postMessage({
        source: 'report-template-link', type: 'bridge-ready',
        data: { protocolVersion: 3, capabilities: ['select', 'bind', 'unbind', 'detect-table'], channelId: channelId }
      }, '*', [channel.port2])
    } catch (_) { /* Direct window messaging remains as a compatibility fallback. */ }
  }

  function bindSelection(command) {
    trace('plugin-bind-start', command)
    var completed = false
    var timeout = window.setTimeout(function () {
      if (!completed) send('bind-error', {
        nonce: command.nonce, message: 'Word 已收到绑定命令，但选区操作未返回'
      })
    }, 8000)
    function finish(type, data) {
      if (completed) return
      completed = true
      window.clearTimeout(timeout)
      send(type, data)
    }
    window.Asc.plugin.executeMethod('GetSelectedText', [{ Numbering: false, Math: true, ParaSeparator: '\n' }], function (text) {
      trace('plugin-bind-selection-read', command)
      text = String(text || '').trim()
      if (!text) {
        finish('bind-error', { nonce: command.nonce, message: '请先在 Word 中选中要绑定的文字，再点击此按钮' })
        return
      }
      window.Asc.plugin.executeMethod('GetCurrentContentControlPr', [], function (current) {
        var currentTag = current && (current.Tag || current.tag) || ''
        var currentId = current && (current.InternalId || current.internalId || current.Id || current.id) || ''
        if (currentTag === command.tag) {
          finish('bind-result', { nonce: command.nonce, control: current, selectedText: text, existing: true })
          return
        }
        if (currentId) {
          finish('bind-error', { nonce: command.nonce, message: '当前文字已属于其他内容控件，请改选未绑定的文字' })
          return
        }
        var properties = {
          Tag: command.tag,
          Alias: command.alias || '',
          Lock: 3,
          Appearance: 1,
          Color: { R: 33, G: 122, B: 103 }
        }
        // Inline controls preserve the paragraph's first-line indent and other formatting.
        window.Asc.plugin.executeMethod('AddContentControl', [1, properties], function (created) {
          if (!created || (created.Tag || created.tag) !== command.tag) {
            finish('bind-error', { nonce: command.nonce, message: 'Word 未能为当前选区创建内容控件，请重新选择文字后再试' })
            return
          }
          function complete() {
            readControls()
            finish('bind-result', { nonce: command.nonce, control: created, selectedText: text, existing: false })
          }
          complete()
        })
      })
    })
  }

  function unbindSelection(command) {
    if (command.id) {
      removeControl(command, command.id)
      return
    }
    window.Asc.plugin.executeMethod('GetCurrentContentControlPr', [], function (current) {
      removeControl(command, itemId(current))
    })
  }

  function removeControl(command, id) {
      if (!id) {
        send('unbind-error', { nonce: command.nonce, message: '请先在 Word 中点击要解除绑定的文字' })
        return
      }
      window.Asc.plugin.executeMethod('RemoveContentControl', [id], function () {
        lastTag = ''
        readControls()
        send('unbind-result', { nonce: command.nonce })
      })
  }

  function pollServerCommand() {
    if (!serviceUrl) return
    fetch(serviceUrl + '/' + encodeURIComponent(channelId) + '?after=' + lastServerCommand, { cache: 'no-store' })
      .then(function (response) { return response.ok ? response.json() : null })
      .then(function (command) {
        if (!command || !command.nonce || command.nonce <= lastServerCommand) return
        lastServerCommand = command.nonce
        receiveHostCommand(command)
      })
      .catch(function () {})
  }

  function connectCommandRelay() {
    fetch('config.json', { cache: 'no-store' })
      .then(function (response) { return response.ok ? response.json() : null })
      .then(function (config) {
        serviceUrl = config && config.serviceUrl || ''
        trace('plugin-relay-configured', {})
      })
      .catch(function () {})
  }

  window.Asc.plugin.init = function () {
    connectHost()
    connectCommandRelay()
    readControls()
    readSelection()
  }
  window.Asc.plugin.button = function () {}
  window.setInterval(processHostCommand, 250)
  window.setInterval(pollServerCommand, 250)
})(window)
