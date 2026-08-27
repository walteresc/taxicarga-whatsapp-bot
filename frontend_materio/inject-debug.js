/**
 * Paste this into browser console to debug timeline rendering
 */

(function debugTimeline() {
  console.log('[DEBUG] === PINIA STORE INSPECTION ===')

  // Find Vue app instance
  const appEl = document.getElementById('app')
  if (!appEl || !appEl.__vue__) {
    console.log('[DEBUG] Vue app not found')
    return
  }

  const app = appEl.__vue__
  console.log('[DEBUG] Vue app:', app)

  // Try to access Pinia store
  if (window.__PINIA__) {
    console.log('[DEBUG] Pinia found:', window.__PINIA__)
  }

  // Monitor ConversationPanel computed
  console.log('\n[DEBUG] === MONITORING COMPUTED ===')

  // Try to get component instance
  const panelEl = document.querySelector('[class*="conversation-panel"]')
  if (panelEl && panelEl.__vue__) {
    const panel = panelEl.__vue__
    console.log('[DEBUG] ConversationPanel instance:', panel)
    console.log('[DEBUG] Props:', panel.props)
    console.log('[DEBUG] Computed messages:', panel.messages)
  }

  // Monitor store directly
  console.log('\n[DEBUG] === STORE STATE ===')

  // Check if store is accessible via app config
  const store = app.$pinia?.state
  if (store && store.messages) {
    console.log('[DEBUG] Store messages:', store.messages.value)
    console.log('[DEBUG] Store messages.value keys:', Object.keys(store.messages.value))
    console.log('[DEBUG] Store messages[1]:', store.messages.value[1])
  }

  // Monitor DOM elements
  console.log('\n[DEBUG] === DOM INSPECTION ===')

  const timeline = document.querySelector('.message-timeline')
  if (timeline) {
    console.log('[DEBUG] Timeline element found')
    console.log('[DEBUG] Timeline visible:', timeline.offsetHeight > 0)
    console.log('[DEBUG] Timeline height:', timeline.offsetHeight)
    console.log('[DEBUG] Timeline children count:', timeline.children.length)
    console.log('[DEBUG] Timeline text:', timeline.innerText?.substring(0, 100))
  } else {
    console.log('[DEBUG] Timeline element NOT FOUND')
  }

  // Check message bubbles
  const bubbles = document.querySelectorAll('.message-bubble')
  console.log('[DEBUG] Message bubbles count:', bubbles.length)

  // Check for empty state
  const emptyState = document.querySelector('.empty-state')
  if (emptyState) {
    console.log('[DEBUG] Empty state found, visible:', emptyState.offsetHeight > 0)
  }

  // Watch for reactivity changes
  console.log('\n[DEBUG] === SETTING UP WATCHERS ===')

  if (store && store.messages) {
    const originalValue = store.messages.value

    // Try to watch changes
    if (typeof Proxy !== 'undefined') {
      const handler = {
        set(target, prop, value) {
          console.log('[DEBUG WATCH] Store.messages.' + prop + ' changed to:', value)
          target[prop] = value
          return true
        }
      }

      store.messages.value = new Proxy(originalValue, handler)
      console.log('[DEBUG] Proxy watcher installed')
    }
  }

  console.log('[DEBUG] === DEBUG SETUP COMPLETE ===')
  console.log('[DEBUG] Now reload the page and select a conversation')
})()
