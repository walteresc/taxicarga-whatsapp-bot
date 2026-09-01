/**
 * Render WhatsApp's own plain-text formatting syntax to HTML for read-only display
 * (message bubbles). Matches WhatsApp's real supported syntax: *bold*, _italic_,
 * ~strikethrough~, "- " bullet lists. There's no cursor to keep aligned here (unlike
 * the composer's live preview), so markers can be safely stripped/replaced.
 */
export function renderWhatsAppText(text) {
  if (!text) return ''

  const escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')

  const lines = escaped.split('\n').map(line => {
    if (line.trim().startsWith('- ')) {
      return `<span class="wa-bullet">• ${line.trim().slice(2)}</span>`
    }

    return line
  })

  const withLists = lines.join('\n')
    .replace(/\*([^*\n]+)\*/g, '<strong>$1</strong>')
    .replace(/_([^_\n]+)_/g, '<em>$1</em>')
    .replace(/~([^~\n]+)~/g, '<s>$1</s>')

  return withLists.replace(/\n/g, '<br>')
}
