/**
 * PASO 1: Browser console script to reproduce layout bug (before/after resize)
 * Usage: Copy/paste into browser DevTools console while on http://localhost:8001/atencion/bandeja-entrada/
 * IMPORTANT: Must be on Vue app route, NOT legacy /dashboard/whatsapp/conversaciones/
 */

(async function paso1() {
  console.log('[PASO 1] === INITIALIZE TEST ===')
  console.log('[PASO 1] Viewport:', window.innerWidth, 'x', window.innerHeight)

  // Verify correct route
  if (!window.location.pathname.includes('/atencion/bandeja-entrada')) {
    console.error('[PASO 1] ✗ WRONG ROUTE!')
    console.error('[PASO 1] You are on:', window.location.pathname)
    console.error('[PASO 1] Must be on: /atencion/bandeja-entrada/')
    
    return
  }
  console.log('[PASO 1] ✓ Correct route: /atencion/bandeja-entrada/')

  // Wait for Vue to be ready
  await new Promise(r => setTimeout(r, 2000))

  console.log('\n[PASO 1] === STATE BEFORE RESIZE ===')

  // Find timeline element
  const timeline = document.querySelector('[data-testid="message-timeline"]')
  const chatContent = document.querySelector('[data-testid="chat-content"]')

  if (!timeline) {
    console.error('[PASO 1] ✗ Timeline not found')
    
    return
  }

  console.log('[PASO 1] Timeline found')

  // Measure BEFORE
  const bboxBefore = timeline.getBoundingClientRect()
  const bubblesBefore = document.querySelectorAll('[data-testid^="message-bubble-"]').length
  const visibleBefore = bboxBefore.height > 0 && bboxBefore.width > 0

  console.log('[PASO 1] BEFORE:')
  console.log('  - Timeline bbox:', {
    top: bboxBefore.top,
    left: bboxBefore.left,
    width: bboxBefore.width,
    height: bboxBefore.height,
  })
  console.log('  - Message bubbles count:', bubblesBefore)
  console.log('  - Timeline visible:', visibleBefore)
  console.log('  - Timeline display:', window.getComputedStyle(timeline).display)
  console.log('  - Timeline flex:', window.getComputedStyle(timeline).flex)
  console.log('  - ChatContent display:', window.getComputedStyle(chatContent).display)

  // Screenshot BEFORE
  html2canvas(document.body, { allowTaint: true, useCORS: true })
    .then(canvas => {
      const link = document.createElement('a')

      link.href = canvas.toDataURL()
      link.download = 'paso1-before-resize.png'
      console.log('[PASO 1] Screenshot BEFORE URL:', link.href.substring(0, 50) + '...')
    })
    .catch(() => console.log('[PASO 1] ⚠️  html2canvas not available'))

  // Wait for user to be ready
  console.log('\n[PASO 1] === READY FOR RESIZE ===')
  console.log('[PASO 1] Press ENTER in console to trigger resize...')

  await new Promise(r => {
    window._paso1Resolve = r
  })

  console.log('\n[PASO 1] === RESIZE VIEWPORT BY 1px ===')
  window.resizeTo(window.outerWidth + 1, window.outerHeight)
  window.dispatchEvent(new Event('resize'))

  // Wait for reflow
  await new Promise(r => {
    requestAnimationFrame(() => {
      setTimeout(r, 500)
    })
  })

  console.log('\n[PASO 1] === STATE AFTER RESIZE ===')

  const bboxAfter = timeline.getBoundingClientRect()
  const bubblesAfter = document.querySelectorAll('[data-testid^="message-bubble-"]').length
  const visibleAfter = bboxAfter.height > 0 && bboxAfter.width > 0

  console.log('[PASO 1] AFTER:')
  console.log('  - Timeline bbox:', {
    top: bboxAfter.top,
    left: bboxAfter.left,
    width: bboxAfter.width,
    height: bboxAfter.height,
  })
  console.log('  - Message bubbles count:', bubblesAfter)
  console.log('  - Timeline visible:', visibleAfter)

  // Comparison
  console.log('\n[PASO 1] === COMPARISON ===')
  console.log('  - Height change:', bboxBefore.height, '→', bboxAfter.height, '(' + (bboxAfter.height - bboxBefore.height) + 'px)')
  console.log('  - Bubbles change:', bubblesBefore, '→', bubblesAfter)
  console.log('  - Visible change:', visibleBefore, '→', visibleAfter)

  // Diagnosis
  console.log('\n[PASO 1] === DIAGNOSIS ===')

  if (bboxBefore.height === 0 && bboxAfter.height > 0) {
    console.log('[PASO 1] ✓ CONFIRMED: Layout initialization bug FIXED')
    console.log('[PASO 1] Timeline height was 0, became positive after resize')
    console.log('[PASO 1] Fix: flex: 1 1 0 added to MessageTimeline.vue CSS')
  } else if (bubblesBefore === 0 && bubblesAfter > 0) {
    console.log('[PASO 1] ⚠️  Bubbles appeared after resize')
  } else if (visibleBefore === visibleAfter && bubblesBefore === bubblesAfter) {
    console.log('[PASO 1] ✓ Layout fix applied: Messages visible immediately')
  } else {
    console.log('[PASO 1] Layout state changed:', { bboxBefore, bboxAfter, bubblesBefore, bubblesAfter })
  }

  console.log('\n[PASO 1] === COMPLETE ===')
})()

// Helper: call window._paso1Resolve() from console to trigger resize
console.log('[PASO 1] Setup complete. Call `window._paso1Resolve()` when ready to trigger resize')
