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

  function readControls(onRead) {
    window.Asc.plugin.executeMethod('GetAllContentControls', [], function (result) {
      controls = Array.isArray(result) ? result : []
      send('controls', controls)
      if (onRead) onRead(controls)
    })
  }

  function waitForControl(tag, onReady, onTimeout, attempt) {
    readControls(function (items) {
      if (items.some(function (item) { return itemTag(item) === tag })) {
        onReady()
        return
      }
      if (attempt >= 20) {
        onTimeout()
        return
      }
      window.setTimeout(function () {
        waitForControl(tag, onReady, onTimeout, attempt + 1)
      }, 150)
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
    else if (command.type === 'update-toc') updateToc(command)
  }

  function updateToc(command) {
    try {
      window.Asc.plugin.callCommand(function () {
        return Api.GetDocument().UpdateAllTOC(true)
      }, false, true, function (result) {
        // UpdateAllTOC returns void in some ONLYOFFICE builds and a boolean
        // in others.  Only an explicit false means the command failed.
        if (result === false) {
          send('update-toc-error', { nonce: command.nonce, message: 'ONLYOFFICE 未能更新目录' })
        } else {
          send('update-toc-result', { nonce: command.nonce })
        }
      })
    } catch (error) {
      send('update-toc-error', { nonce: command.nonce, message: String(error) })
    }
  }

  function detectTable(command) {
    var methods = ['GetCurrentTableIndex', 'GetCurrentTable', 'GetCurrentTablePr']
    function read(result) {
      var value = result && (result.index || result.Index || result.tableIndex || result.TableIndex)
      var index = typeof result === 'number' ? result : Number(value)
      if (index > 0) { send('table-detect-result', { nonce: command.nonce, index: index }); return true }
      return false
    }
    function next(position) {
      if (position >= methods.length) {
        send('table-detect-error', { nonce: command.nonce, message: 'OnlyOffice 未返回当前表格序号，请将光标放在目标表格内' })
        return
      }
      try {
        window.Asc.plugin.executeMethod(methods[position], [], function (result) {
          if (!read(result)) next(position + 1)
        })
      } catch (_) { next(position + 1) }
    }
    next(0)
  }

  window.addEventListener('message', function (event) {
    receiveHostCommand(event.data)
  })

  function connectHost() {
    var ready = {
      source: 'report-template-link', type: 'bridge-ready',
      data: { protocolVersion: 3, capabilities: ['select', 'bind', 'unbind', 'detect-table', 'update-toc'], channelId: channelId }
    }
    try {
      var channel = new MessageChannel()
      hostPort = channel.port1
      hostPort.onmessage = function (event) { receiveHostCommand(event.data) }
      hostPort.start()
      window.top.postMessage(ready, '*', [channel.port2])
    } catch (_) { /* The plain announcement below does not need a transferable port. */ }
    var attempts = 0
    var announcement = window.setInterval(function () {
      window.top.postMessage(ready, '*')
      trace('plugin-bridge-announced', {})
      if (++attempts >= 15) window.clearInterval(announcement)
    }, 1000)
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
    function continueBinding(selectionType, text) {
      trace('plugin-bind-selection-read', command)
      window.Asc.plugin.executeMethod('GetCurrentContentControlPr', [], function (current) {
        var currentTag = current && (current.Tag || current.tag) || ''
        var currentId = current && (current.InternalId || current.internalId || current.Id || current.id) || ''
        if (currentTag === command.tag) {
          finish('bind-result', { nonce: command.nonce, control: current, selectedText: text, existing: true,
            objectType: selectionType === 'drawing' ? 'image' : 'text' })
          return
        }
        if (currentId) {
          finish('bind-error', { nonce: command.nonce, message: '当前对象已属于其他内容控件，请改选未绑定的文字或图片' })
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
        var method = selectionType === 'drawing' ? 'AddContentControlPicture' : 'AddContentControl'
        var args = selectionType === 'drawing' ? [properties] : [1, properties]
        window.Asc.plugin.executeMethod(method, args, function (created) {
          if (!created || (created.Tag || created.tag) !== command.tag) {
            finish('bind-error', { nonce: command.nonce, message: 'Word 未能为当前选区创建内容控件，请重新选择文字或图片后再试' })
            return
          }
          // Only report success after Word confirms that the new control is
          // visible through GetAllContentControls. This keeps the host's
          // force-save request behind the editor mutation instead of racing it.
          waitForControl(command.tag, function () {
            trace('plugin-bind-controls-read', command)
            finish('bind-result', { nonce: command.nonce, control: created, selectedText: text, existing: false,
              objectType: selectionType === 'drawing' ? 'image' : 'text' })
          }, function () {
            finish('bind-error', { nonce: command.nonce, message: 'Word 已创建控件，但控件列表尚未同步，请稍后重试' })
          }, 0)
        })
      })
    }
    window.Asc.plugin.executeMethod('GetSelectionType', [], function (rawSelectionType) {
      var selectionType = normalizeSelectionType(rawSelectionType)
      trace('plugin-bind-selection-type', { nonce: command.nonce, type: String(rawSelectionType || '') })
      if (selectionType === 'image') {
        continueBinding('drawing', '')
        return
      }
      if (selectionType !== 'text') {
        finish('bind-error', { nonce: command.nonce, message: 'Word 未返回可绑定的文字或图片选区，请重新选择后再试' })
        return
      }
      window.Asc.plugin.executeMethod('GetSelectedText', [{ Numbering: false, Math: true, ParaSeparator: '\n' }], function (text) {
        text = String(text || '').trim()
        if (!text) {
          trace('plugin-bind-empty-text', command)
          continueBinding('drawing', '')
          return
        }
        continueBinding('text', text)
      })
    })
  }

  function normalizeSelectionType(value) {
    var raw = value && typeof value === 'object'
      ? (value.type || value.Type || value.value)
      : value
    var normalized = String(raw || '').trim().toLowerCase()
    if (normalized === 'text') return 'text'
    if (['drawing', 'image', 'picture'].indexOf(normalized) >= 0) return 'image'
    return ''
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
