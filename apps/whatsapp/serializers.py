"""Serializers for WhatsApp messaging and multimedia."""

from rest_framework import serializers

from .models import MensajeAdjunto, MensajeWhatsApp, ConversacionWhatsApp


class MensajeAdjuntoSerializer(serializers.ModelSerializer):
    """Attachment metadata serializer - for multimedia files."""

    # Include file URL for frontend access
    archivo_url = serializers.SerializerMethodField()

    class Meta:
        model = MensajeAdjunto
        fields = [
            'id',
            'ycloud_media_id',
            'formato',
            'mime_type',
            'filename',
            'file_size',
            'sha256',
            'storage_location',
            'archivo',
            'archivo_url',
            'downloaded_at',
            'retention_policy',
            'retain_until',
            'protected_from_cleanup',
            'ia_analysis_result',
            'created_at',
        ]
        read_only_fields = [
            'id',
            'ycloud_media_id',
            'sha256',
            'downloaded_at',
            'archivo',
            'archivo_url',
            'created_at',
        ]

    def get_archivo_url(self, obj):
        """Return the file URL if available."""
        if obj.archivo:
            return obj.archivo.url
        return None


class MensajeWhatsAppSerializer(serializers.ModelSerializer):
    """Message serializer with multimedia support."""

    # Nested serialization for attachments
    adjuntos = MensajeAdjuntoSerializer(many=True, read_only=True)

    # Display choices as labels
    tipo_display = serializers.CharField(source='get_tipo_display', read_only=True)
    direccion_display = serializers.CharField(source='get_direccion_display', read_only=True)
    origen_display = serializers.CharField(source='get_origen_display', read_only=True)
    estado_display = serializers.CharField(source='get_estado_display', read_only=True)
    media_status_display = serializers.CharField(source='get_media_status_display', read_only=True)
    sender_type_display = serializers.CharField(source='get_sender_type_display', read_only=True)
    source_display = serializers.CharField(source='get_source_display', read_only=True)

    class Meta:
        model = MensajeWhatsApp
        fields = [
            # Identity
            'id',
            'meta_message_id',

            # Message properties
            'tipo',
            'tipo_display',
            'direccion',
            'direccion_display',
            'origen',
            'origen_display',
            'sender_type',
            'sender_type_display',
            'source',
            'source_display',

            # Content
            'contenido',
            'caption',

            # Media
            'ycloud_media_id',
            'mime_type',
            'filename',
            'file_size',
            'sha256',
            'media_status',
            'media_status_display',
            'adjuntos',

            # Status
            'estado',
            'estado_display',
            'error_codigo',
            'error_detalle',

            # Retention
            'retention_policy',
            'retain_until',
            'protected_from_cleanup',
            'protection_reason',

            # Timestamps
            'fecha_mensaje',
            'entregado_en',
            'leido_en',
            'creado_en',

            # Relations
            'autor',
            'conversacion',
        ]
        read_only_fields = [
            'id',
            'meta_message_id',
            'creado_en',
            'conversacion',
            'autor',
            'adjuntos',
        ]

    def to_representation(self, instance):
        """Custom representation for frontend consumption."""
        data = super().to_representation(instance)

        # For non-multimedia messages, omit empty media fields
        if instance.tipo == "texto":
            for field in ['ycloud_media_id', 'mime_type', 'filename', 'file_size', 'sha256', 'adjuntos']:
                if not data.get(field):
                    data.pop(field, None)

        return data


class ConversacionWhatsAppSerializer(serializers.ModelSerializer):
    """Conversation serializer with message history."""

    mensajes = MensajeWhatsAppSerializer(many=True, read_only=True)
    estado_atencion_display = serializers.CharField(source='get_estado_atencion_display', read_only=True)
    estado_recopilacion_display = serializers.CharField(source='get_estado_recopilacion_display', read_only=True)
    estado_cotizacion_display = serializers.CharField(source='get_estado_cotizacion_display', read_only=True)

    class Meta:
        model = ConversacionWhatsApp
        fields = [
            'id',
            'cliente',
            'lead',
            'channel',
            'estado_atencion',
            'estado_atencion_display',
            'estado_recopilacion',
            'estado_recopilacion_display',
            'estado_cotizacion',
            'estado_cotizacion_display',
            'bot_pausado',
            'instruccion_retorno_bot',
            'resumen',
            'datos_faltantes',
            'porcentaje_informacion',
            'motivo_derivacion',
            'responsable',
            'ultima_actividad',
            'ultimo_mensaje_cliente',
            'ultimo_mensaje_enviado',
            'cerrada_en',
            'mensajes',
            'creada_en',
            'actualizada_en',
        ]
        read_only_fields = [
            'id',
            'creada_en',
            'actualizada_en',
            'mensajes',
        ]
