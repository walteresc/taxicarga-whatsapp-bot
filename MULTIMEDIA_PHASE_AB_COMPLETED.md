# Multimedia Support - Phase A & B Implementation

**Date:** 2026-08-20  
**Status:** ✅ COMPLETED  
**Next:** Phase C - Webhook integration + First vertical delivery (images)

---

## Phase A: Model Extension (Completed)

### Changes to MensajeWhatsApp

Added multimedia fields to existing model via non-destructive migration `0014_extend_mensaje_multimedia`:

**Media Content:**
- `ycloud_media_id` - YCloud media ID for tracking
- `mime_type` - Validated MIME type (server-side, not client-provided)
- `filename` - Safe filename generated server-side
- `file_size` - File size in bytes
- `sha256` - SHA256 hash for integrity verification
- `caption` - User caption for images/videos/documents

**Status Tracking:**
- `media_status` - (pending|downloading|ready|failed|expired)

**Classification:**
- `sender_type` - (customer|bot|advisor|system) for UI filtering
- `source` - (whatsapp_api|whatsapp_web|crm|webhook) origin tracking

**Retention Policy:**
- `retention_policy` - (default:30d|quote:60d|service:90d|claim:unlimited|none)
- `retain_until` - Expiration date for cleanup
- `protected_from_cleanup` - Manual protection flag

**Manual Protection:**
- `protection_reason` - Why protected
- `protected_by` - User who protected
- `protection_date` - When protected

**Migration:** `0014_extend_mensaje_multimedia`  
**Breaking Changes:** None - all fields nullable with sensible defaults

---

## Phase B: Attachment Tracking Model (Completed)

### New Model: MensajeAdjunto

Created dedicated model for multimedia file metadata via migration `0015_create_mensaje_adjunto`:

**Structure:**
```python
class MensajeAdjunto(models.Model):
    mensaje → ForeignKey(MensajeWhatsApp)
    ycloud_media_id → CharField(unique, indexed)
    formato → (imagen|video|audio|documento)
    mime_type, filename, file_size, sha256
    archivo → FileField(upload_to=whatsapp/multimedia/%Y/%m/)
    
    storage_location → (ycloud|local)
    downloaded_at → Timestamp
    download_attempts → Count
    last_download_error → Text
    
    retention_policy, retain_until, protected_from_cleanup
    ia_analysis_result → JSON (persists after file deleted)
    created_at, updated_at
```

**Key Features:**
- One MensajeWhatsApp can have multiple adjuntos (e.g., carousel/document with images)
- IA analysis results persist even if file is cleaned up
- Download retry tracking for resilience
- Cascading delete: removing message deletes adjuntos too

**Indexes:**
- `(mensaje, -created_at)` - Fast message→adjuntos queries
- `(retain_until, protected_from_cleanup)` - Fast cleanup queries
- `ycloud_media_id` - Idempotence checking
- `sha256` - Integrity verification

---

## Serializers (New File)

**File:** `apps/whatsapp/serializers.py`

### MensajeAdjuntoSerializer
- Includes `archivo_url` computed field for frontend access
- Read-only: id, ycloud_media_id, sha256, downloaded_at, archivo
- Exposes all metadata for chat rendering

### MensajeWhatsAppSerializer
- Nested `adjuntos` (MensajeAdjuntoSerializer)
- Display choice labels for all choice fields
- Omits empty media fields for text-only messages
- Supports multimedia-aware API responses

### ConversacionWhatsAppSerializer
- Nested `mensajes` (MensajeWhatsAppSerializer)
- Full conversation history with multimedia

---

## Secure Download Service (Phase C Prep)

**File:** `apps/whatsapp/services.py`

### Function: `download_mensaje_adjunto(...)`

**Security Enforced:**
- ✅ Never expose `YCLOUD_API_KEY` (Bearer token in headers, not returned)
- ✅ Only download from YCloud expected domains (domain validation)
- ✅ Validate MIME type real type (header magic bytes, not client-provided)
- ✅ Stream downloads with size limits (8KB chunks, MAX_IMAGE_BYTES / MAX_ATTACHMENT_BYTES)
- ✅ Generate safe filenames server-side (no user input in filename)
- ✅ Calculate SHA256 for integrity verification
- ✅ Idempotent: checks if media_id already downloaded (prevents duplicates)

**Process:**
1. Validate download URL domain (whitelist: api.ycloud.com, download.ycloud.com)
2. Check if already downloaded (by ycloud_media_id)
3. Download with retry logic (3 attempts)
4. Stream content while calculating SHA256
5. Validate MIME type from content
6. Generate safe filename (media_id + extension)
7. Calculate retention date based on policy
8. Save to MEDIA_ROOT with FileField
9. Create MensajeAdjunto with all metadata
10. Update MensajeWhatsApp.media_status to READY
11. Return adjunto_id for reference

**Retention Dates:**
- Default: now + 30 days
- Quote-linked: now + 60 days
- Service-linked: now + 90 days
- Claim: now + 10 years
- None: no automatic cleanup

---

## Management Commands

### 1. `download_pending_multimedia.py`

Download queued multimedia from YCloud.

**Usage:**
```bash
# Dry-run (safe to run anytime)
python manage.py download_pending_multimedia --dry-run

# Download up to 50 files
python manage.py download_pending_multimedia

# Download only images
python manage.py download_pending_multimedia --formato imagen

# Limit to 10 files
python manage.py download_pending_multimedia --limit 10
```

**For Cron:**
```bash
# Download every 5 minutes
*/5 * * * * cd /path && python manage.py download_pending_multimedia

# Download every hour
0 * * * * cd /path && python manage.py download_pending_multimedia --limit 100
```

**Behavior:**
- Queries MensajeWhatsApp with media_status in (pending, downloading)
- Requires `ycloud_media_id` populated
- Sets status to DOWNLOADING before attempting download
- On success: creates MensajeAdjunto, sets status to READY
- On failure: sets status to FAILED, logs error

### 2. `cleanup_expired_multimedia.py`

Delete expired files according to retention policies.

**Usage:**
```bash
# Dry-run (ALWAYS RUN THIS FIRST!)
python manage.py cleanup_expired_multimedia --dry-run

# Actual cleanup
python manage.py cleanup_expired_multimedia

# Keep files 7 days longer (safety buffer)
python manage.py cleanup_expired_multimedia --keep-days 7
```

**For Cron (Daily):**
```bash
# 2 AM: Dry-run (email results)
0 2 * * * cd /path && python manage.py cleanup_expired_multimedia --dry-run > /var/log/cleanup_dryrun.log 2>&1

# 3 AM: Actual cleanup
0 3 * * * cd /path && python manage.py cleanup_expired_multimedia > /var/log/cleanup.log 2>&1
```

**Safety Features:**
- Respects `protected_from_cleanup` flag
- Deletes file + database record atomically
- Dry-run shows what would be deleted
- Breakdown by retention policy
- Error resilience (continues on failure)
- Comprehensive logging

---

## Database Schema Summary

### MensajeWhatsApp Changes
- Before: 17 fields (text-only)
- After: 37 fields (multimedia-ready)
- No data loss (all new fields have defaults)
- Existing queries still work unchanged

### New: MensajeAdjunto Table
- 22 fields
- Cascades to MensajeWhatsApp
- Indexed on: ycloud_media_id, (mensaje, created_at), (retain_until, protected_from_cleanup)

### Migration Path
- ✅ 0014: Add fields to MensajeWhatsApp (non-destructive)
- ✅ 0015: Create MensajeAdjunto + indexes
- No schema changes to legacy models (Conversacion, EvidenciaWhatsapp)

---

## Next Steps: Phase C

### Webhook Integration
1. Update `apps/whatsapp/views._receive_message()` to:
   - Create MensajeWhatsApp with media metadata
   - Queue adjunto download (via management command)
   - Return HTTP 200 immediately (don't block on download)

2. For each media type (imagen → video → audio → documento):
   - Extract media_id, URL, MIME type from event
   - Populate ycloud_media_id, media_status=pending
   - Trigger download via management command

### Vue Component Integration
1. Create `MensajeMedia.vue` component
2. Route by `tipo` → (imagen|video|audio|document)
3. Use `archivo_url` from serializer
4. Handle loading states, errors, retention warnings

### Testing
- Unit tests for `download_mensaje_adjunto()`
- Integration tests for webhook → MensajeAdjunto flow
- Dry-run cleanup tests
- Security tests (domain validation, MIME detection)

### Deployment Checklist
- [ ] Add cron jobs for download_pending_multimedia & cleanup_expired_multimedia
- [ ] Set YCLOUD_API_KEY in production .env
- [ ] Create MEDIA_ROOT/whatsapp/multimedia/ directory
- [ ] Verify permissions (Django process can write files)
- [ ] Test download with real YCloud URL
- [ ] Monitor cleanup logs for 7 days
- [ ] Verify file cleanup is removing expired files

---

## Files Changed / Created

### Modified
- `apps/whatsapp/models.py` - Extended MensajeWhatsApp + new MensajeAdjunto
- `apps/whatsapp/services.py` - Added download_mensaje_adjunto() + security

### Created
- `apps/whatsapp/serializers.py` - API serializers for multimedia
- `apps/whatsapp/migrations/0014_extend_mensaje_multimedia.py`
- `apps/whatsapp/migrations/0015_create_mensaje_adjunto.py`
- `apps/whatsapp/management/commands/download_pending_multimedia.py`
- `apps/whatsapp/management/commands/cleanup_expired_multimedia.py`

### Not Modified
- `apps/clientes/models.py` - Conversacion stays as-is
- `apps/whatsapp/views.py` - Will be updated in Phase C
- `frontend_materio/` - Will be updated in Phase C

---

## Security Checklist

- ✅ YCLOUD_API_KEY never in response
- ✅ YCLOUD_API_KEY never in logs
- ✅ YCLOUD_API_KEY only in Bearer header
- ✅ Domain whitelist for downloads (no arbitrary URLs)
- ✅ MIME type validation from content, not client header
- ✅ Filename sanitization (server-generated, no user input)
- ✅ SHA256 integrity verification
- ✅ Size limits (10MB images, 25MB other)
- ✅ Streaming downloads (no full buffer in RAM)
- ✅ Retention policies enforced
- ✅ Manual protection option
- ✅ Idempotent downloads (no duplication)
- ✅ Error logging without exposing secrets

---

## Notes

- All multimedia support is non-destructive and runs alongside existing Conversacion model
- MensajeWhatsApp can be empty (media_status=pending) while webhook processes, filled in later by management command
- IA analysis results persist even after file cleanup (recorded in ia_analysis_result JSON)
- Webhook will NOT block on downloads - returns 200 immediately, downloads happen async via cron
- Supports multiple media types in single message (e.g., carousel items would be separate MensajeAdjunto)

---

**Authored:** Claude Code (2026-08-20)  
**Environment:** Django 6.0.6, Python 3.10+, SQLite (dev) / PostgreSQL (prod)  
**Status:** Ready for Phase C - Webhook integration + vertical delivery
