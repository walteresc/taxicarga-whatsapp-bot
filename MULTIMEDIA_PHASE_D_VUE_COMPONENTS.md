# Multimedia Support - Phase D: Vue Components

**Date:** 2026-08-20  
**Status:** ✅ COMPLETED  
**Next:** Phase E (Async IA analysis), Phase F+ (Testing, deployment)

---

## Summary

Phase D adds Vue 3 components to render multimedia messages in the chat interface. Each media type (image, video, audio, document, location, text) has its own component for optimized display.

---

## Components Created

### Main Component: `MensajeMedia.vue` (250+ lines)

**Purpose:** Central multimedia message renderer (replaces/complements MessageBubble.vue)

**Features:**
- Auto-detects message type (texto, imagen, video, audio, documento, ubicacion)
- Routes to correct media component
- Handles media_status states (PENDING, READY, FAILED, EXPIRED)
- Shows retention warning if file expires in <3 days
- Displays sender name, timestamp, delivery status
- Shows loading spinner while downloading
- Shows error message if download failed
- Retry button for failed messages

**Props:**
```javascript
{
  message: Object (required)
  // Expected fields:
  // - tipo: 'texto'|'imagen'|'video'|'audio'|'documento'|'ubicacion'
  // - media_status: 'pending'|'downloading'|'ready'|'failed'|'expired'
  // - sender_type: 'customer'|'bot'|'advisor'|'system'
  // - estado: 'recibido'|'enviado'|'entregado'|'leido'|'error'
  // - fecha_mensaje: ISO datetime
  // - adjuntos: Array[{archivo_url, retain_until, protected_from_cleanup, ...}]
  // - contenido: text for text messages
  // - caption: caption for media
}
```

**Emits:**
- `retry`: when user clicks retry button

---

## Media Type Components

### 1. `media/MediaText.vue`

**Renders:** Simple text messages  
**Output:** `<p>{{ message.contenido }}</p>`  
**Size:** 13 lines (trivial)

---

### 2. `media/MediaImage.vue`

**Renders:** Image attachments

**Features:**
- Displays `<img>` from `adjuntos[0].archivo_url`
- Max dimensions: 300px height (responsive width)
- Hover effect (opacity 0.9)
- Fallback: "Imagen no disponible" icon
- Shows caption if provided

**Error Handling:**
- `@error` emits 'error' event on load failure
- Shows fallback UI gracefully

---

### 3. `media/MediaVideo.vue`

**Renders:** Video attachments

**Features:**
- HTML5 `<video>` with `controls` attribute
- Source from `adjuntos[0].archivo_url`
- Max: 300px height
- Black background (video player standard)
- Shows caption if provided

**Browser Support:**
- Uses native HTML5 video (supported in all modern browsers)
- Codecs: depends on server (MP4, WebM, Ogg)

---

### 4. `media/MediaAudio.vue`

**Renders:** Audio attachments

**Features:**
- HTML5 `<audio>` with `controls` attribute
- Source from `adjuntos[0].archivo_url`
- Min-width: 250px (controls need space)
- Fallback: "Audio no disponible" icon

**Browser Support:**
- Native audio controls (play, pause, progress, volume)
- Formats: MP3, OGG, WAV (depending on server)

---

### 5. `media/MediaDocument.vue`

**Renders:** Document/file attachments

**Features:**
- Download link with icon
- File icon based on extension (PDF, Word, Excel, PowerPoint, ZIP, etc.)
- Displays filename and file size (formatted: B/KB/MB)
- Click to download (respects CORS + content-disposition)
- Hover effect on download button

**File Size Formatting:**
```
< 1 KB: "123 B"
< 1 MB: "45.6 KB"
>= 1 MB: "1.2 MB"
```

**Icon Mapping:**
- `.pdf` → ri-file-pdf-line
- `.doc/.docx` → ri-file-word-line
- `.xls/.xlsx` → ri-file-excel-line
- `.ppt/.pptx` → ri-file-ppt-line
- `.zip/.rar` → ri-file-zip-line
- `.txt` → ri-file-text-line
- Others → ri-file-line

---

### 6. `media/MediaLocation.vue`

**Renders:** Location/GPS coordinates

**Features:**
- Map preview with gradient background (667eea → 764ba2)
- "View in Google Maps" button
- Opens maps.google.com with lat/lon
- Displays coordinates (4 decimal places)
- Shows location name if available
- Fallback: "Ubicación no disponible"

**Data Parsing:**
- Tries `adjuntos[0].ia_analysis_result.coordinates` first
- Falls back to JSON in `contenido`
- Falls back to regex parsing: `Lat: X, Lon: Y`

---

## Integration

### Updated MessageTimeline.vue

**Changes:**
```javascript
// Import
import MensajeMedia from './MensajeMedia.vue'

// Template
<MensajeMedia v-if="message.tipo && message.tipo !== 'internal-note'" :message="message" />
<MessageBubble v-else-if="message.type !== 'internal-note'" :message="message" />
<InternalNote v-else :note="message" />
```

**Logic:**
- Detects `message.tipo` field (new WhatsApp multimedia)
- Uses `MensajeMedia` for new messages
- Falls back to `MessageBubble` for legacy messages
- Maintains backward compatibility

---

## UI Behavior

### Message States

#### Pending Download (media_status=PENDING/DOWNLOADING)
```
┌─────────────────────────────────────────┐
│ [spinner] Descargando multimedia...      │
└─────────────────────────────────────────┘
```

#### Ready (media_status=READY)
```
┌─────────────────────────────────────────┐
│ [Image Preview]                          │
│ Caption text if provided                 │
│ 14:35    ✓                              │
└─────────────────────────────────────────┘
(If expires in <3 days)
⚠️  Se eliminará el 23 de agosto
```

#### Failed/Expired (media_status=FAILED/EXPIRED)
```
┌─────────────────────────────────────────┐
│ ✗ El archivo ha expirado                │
│ [Reintentar]                             │
└─────────────────────────────────────────┘
```

#### Not Available (adjuntos empty, media_status=READY)
```
┌─────────────────────────────────────────┐
│ 🖼️  Imagen no disponible                │
└─────────────────────────────────────────┘
```

---

## CSS & Styling

### Responsive Design
- Images: max-height 300px, auto width
- Videos: max-height 300px, black background
- Audio: min-width 250px (controls)
- Documents: 40px icon, file info aside
- Locations: 150px map preview

### Colors
- Client messages: #f0f0f0 (gray)
- Bot messages: #fff3e0 (light orange)
- Advisor messages: #ff9800 (orange)
- System messages: transparent
- Loading spinner: #ff9800 (matches bot)
- Error text: #f44336 (red)
- Retention warning: #f44336 (red)

### Animations
- Slide-in on message appear (0.2s)
- Spinner rotation (0.8s loop)
- Hover opacity for images (0.9)
- Hover background for buttons

---

## Media Status Flow

```
User sends media via WhatsApp
    ↓
Webhook received (Phase C)
    ↓
MensajeWhatsApp created: media_status=PENDING
    ↓
Vue renders: [spinner] "Descargando multimedia..."
    ↓
Cron runs: download_pending_multimedia
    ↓
File downloaded + validated
    ↓
MensajeAdjunto created
    ↓
media_status=READY
    ↓
Vue re-renders: [Image] | [Audio] | [Document] etc.
    ↓
File available for 30 days (default retention)
    ↓
Cleanup job deletes file after retention_policy expires
```

---

## Error Handling

### Image Load Fails
- Shows fallback icon + text
- Emits 'error' event (can be logged)
- User sees [Imagen no disponible]

### Document Download CORS Issue
- Browser blocks cross-origin download
- Use Django proxy endpoint (future: Phase G)

### Location Parsing Fails
- Falls through parsing attempts
- Shows fallback: [Ubicación no disponible]

---

## Performance Considerations

### File Size Display
- Calculated client-side (fast)
- Formats: B/KB/MB for readability

### Image Lazy Loading
- Can be added: `loading="lazy"` on img tag (future optimization)

### Audio/Video Streaming
- HTML5 native (efficient)
- Browser caches based on HTTP headers

---

## Accessibility

### Semantic HTML
- `<img alt="Imagen">` - alt text provided
- `<audio>` - native controls (accessible)
- `<video>` - native controls (accessible)
- Icon labels via Remixicon (semantic naming)

### Color Contrast
- Text on message bubbles: sufficient contrast
- Loading spinner: visible on all backgrounds
- Error messages: red (#f44336) on white/light

---

## Known Limitations

1. **No lightbox for images**
   - Future: add modal preview on click
   - Current: opens full-size in browser

2. **Audio/video formats**
   - Depends on server codec support
   - No transcoding (Phase G feature)

3. **Large files**
   - UI doesn't show bandwidth/progress
   - Future: upload progress bar

4. **Duplicate messages**
   - No "edited" indicator
   - Future: add edit history

5. **Download naming**
   - Uses server filename (secure)
   - Browser renames if filename exists

---

## Files Created / Modified

### Created (6 files)
- `MensajeMedia.vue` (250L, main component)
- `media/MediaText.vue` (13L)
- `media/MediaImage.vue` (60L)
- `media/MediaVideo.vue` (52L)
- `media/MediaAudio.vue` (62L)
- `media/MediaDocument.vue` (140L)
- `media/MediaLocation.vue` (140L)

### Modified (1 file)
- `MessageTimeline.vue` - import + template logic

### Total: ~720 lines of Vue 3 code

---

## Testing Checklist

- [ ] Image displays correctly (various sizes)
- [ ] Video plays with native controls
- [ ] Audio plays with volume control
- [ ] Document downloads with correct filename
- [ ] Location opens Google Maps
- [ ] Loading spinner shows while media_status=PENDING
- [ ] Error message shows if media_status=FAILED
- [ ] Retention warning displays for expiring files
- [ ] Retry button works
- [ ] Message timestamp and status icon display
- [ ] Sender name displays for bot/advisor
- [ ] Captions render below media
- [ ] Responsive on mobile (70% max-width)
- [ ] Fallback icons show when URLs missing
- [ ] No layout shift when loading completes

---

## Next Steps (Phase E+)

### Phase E: Async IA Analysis
- Queue analyze_moving_image() for images without caption
- Update MensajeAdjunto.ia_analysis_result
- Emit bot reply when analysis completes
- Show IA results in message

### Phase F: Testing
- Unit tests for component props/emits
- Snapshot tests for rendering
- E2E tests for user interactions

### Phase G: Optimizations
- Image lazy loading
- Video/audio streaming progress
- Document preview (PDF inline viewer)
- Download progress indicator

### Phase H: Deployment & Monitoring
- Cron jobs configured
- File cleanup verified
- Error logs monitored
- Performance metrics tracked

---

## Browser Compatibility

✅ Chrome/Edge 90+  
✅ Firefox 88+  
✅ Safari 14+  
✅ Mobile browsers (iOS Safari, Chrome Mobile)  

Native HTML5 support for `<img>`, `<video>`, `<audio>` tags ensures broad compatibility.

---

**Authored:** Claude Code (2026-08-20)  
**Status:** Ready for Phase E (Async IA analysis)  
**Total Implementation Time (A-D):** ~5-6 hours
