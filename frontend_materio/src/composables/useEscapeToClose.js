import { onBeforeUnmount, onMounted } from 'vue'

// Cierra con Escape solo el modal que está arriba de todo (respeta el
// apilamiento: si hay un modal sobre otro, Escape cierra primero el de encima).
const stack = []
let listening = false

const handler = e => {
  if (e.key !== 'Escape' || !stack.length) return
  // El de mayor prioridad (más al frente); a igualdad, el último montado.
  let top = null
  for (const entry of stack) {
    if (entry.disabled?.()) continue
    if (!top || (entry.priority ?? 0) >= (top.priority ?? 0)) top = entry
  }
  if (!top) return
  e.stopPropagation()
  top.close()
}

export function useEscapeToClose(close, opts = {}) {
  const entry = { close, disabled: opts.disabled, priority: opts.priority ?? 0 }
  onMounted(() => {
    stack.push(entry)
    if (!listening) {
      window.addEventListener('keydown', handler)
      listening = true
    }
  })
  onBeforeUnmount(() => {
    const i = stack.indexOf(entry)
    if (i >= 0) stack.splice(i, 1)
  })
}
