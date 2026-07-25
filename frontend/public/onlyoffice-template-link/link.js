(function (window) {
  'use strict'
  var controls = []
  var lastTag = ''
  var lastCommand = 0
  var lastRemoteCommand = 0
  var remoteInitialized = false

  function send(type, data) {
    try {
      window.top.postMessage({ source: 'report-template-link', type: type, data: data || null }, '*')
    } catch (_) { /* The host can still use one-way rule-to-Word navigation. */ }
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
    var control = controls.find(function (item) {
      return (command.id && (item.InternalId === command.id || item.Id === command.id)) ||
        (command.tag && (item.Tag === command.tag || item.tag === command.tag))
    })
    var id = control && (control.InternalId || control.Id)
    if (id) window.Asc.plugin.executeMethod('SelectContentControl', [id])
  }

  function bindSelection(command) {
    window.Asc.plugin.executeMethod('GetSelectedText', [{ Numbering: false, Math: true, ParaSeparator: '\n' }], function (text) {
      text = String(text || '').trim()
      if (!text) {
        send('bind-error', { nonce: command.nonce, message: '请先在 Word 中选中要绑定的文字，再点击此按钮' })
        return
      }
      window.Asc.plugin.executeMethod('GetCurrentContentControlPr', [], function (current) {
        var currentTag = current && (current.Tag || current.tag) || ''
        var currentId = current && (current.InternalId || current.internalId || current.Id || current.id) || ''
        if (currentTag === command.tag) {
          send('bind-result', { nonce: command.nonce, control: current, selectedText: text, existing: true })
          return
        }
        if (currentId) {
          send('bind-error', { nonce: command.nonce, message: '当前文字已属于其他内容控件，请改选未绑定的文字' })
          return
        }
        var properties = {
          Tag: command.tag,
          Alias: command.alias || '',
          Lock: 3,
          Appearance: 1,
          Color: { R: 33, G: 122, B: 103 }
        }
        window.Asc.plugin.executeMethod('AddContentControl', [2, properties], function (created) {
          if (!created || (created.Tag || created.tag) !== command.tag) {
            send('bind-error', { nonce: command.nonce, message: 'Word 未能为当前选区创建内容控件，请重新选择文字后再试' })
            return
          }
          function complete() {
            readControls()
            send('bind-result', { nonce: command.nonce, control: created, selectedText: text, existing: false })
          }
          if (command.oldInternalId && command.oldInternalId !== (created.InternalId || created.Id)) {
            window.Asc.plugin.executeMethod('RemoveContentControl', [command.oldInternalId], complete)
          } else complete()
        })
      })
    })
  }

  function unbindSelection(command) {
    window.Asc.plugin.executeMethod('GetCurrentContentControlPr', [], function (current) {
      var currentId = current && (current.InternalId || current.internalId || current.Id || current.id) || ''
      if (!currentId) {
        send('unbind-error', { nonce: command.nonce, message: '请先在 Word 中点击要解除绑定的文字' })
        return
      }
      window.Asc.plugin.executeMethod('RemoveContentControl', [currentId], function () {
        lastTag = ''
        readControls()
        send('unbind-result', { nonce: command.nonce })
      })
    })
  }

  function pollRemoteCommand() {
    fetch('/api/v1/admin/onlyoffice/command?after=' + lastRemoteCommand, { cache: 'no-store' })
      .then(function (response) { return response.ok ? response.json() : null })
      .then(function (command) {
        if (!command || !command.nonce || command.nonce <= lastRemoteCommand) return
        lastRemoteCommand = command.nonce
        if (command.type === 'bind') bindSelection(command)
        else if (command.type === 'unbind') unbindSelection(command)
      })
      .catch(function () {})
  }

  function initializeRemoteCommands() {
    if (remoteInitialized) return
    remoteInitialized = true
    fetch('/api/v1/admin/onlyoffice/command?after=0', { cache: 'no-store' })
      .then(function (response) { return response.ok ? response.json() : null })
      .then(function (command) {
        lastRemoteCommand = command && command.nonce || 0
      })
      .catch(function () {})
      .then(function () {
        readControls()
        window.setInterval(pollRemoteCommand, 250)
      })
  }

  window.Asc.plugin.init = function () {
    initializeRemoteCommands()
    readSelection()
  }
  window.Asc.plugin.button = function () {}
  window.setInterval(processHostCommand, 250)
  window.setInterval(readSelection, 650)
})(window)
