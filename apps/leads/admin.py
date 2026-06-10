from django.contrib import admin, messages
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from .models import Lead


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = (
        "cliente",
        "telefono",
        "ruta",
        "tipo_servicio",
        "estado",
        "etapa_conversacion",
        "prioridad",
        "atencion_humana",
        "requiere_asesor",
        "bot_pausado",
        "precio_recomendado",
        "vendedor_asignado",
        "fecha_servicio",
        "fecha_proximo_seguimiento",
        "fecha_creacion",
    )
    list_filter = (
        "estado",
        "etapa_conversacion",
        "prioridad",
        "atencion_humana",
        "requiere_asesor",
        "bot_pausado",
        "tipo_servicio",
        "vendedor_asignado",
        "fecha_servicio",
        "fecha_proximo_seguimiento",
        "fecha_creacion",
    )
    search_fields = (
        "cliente__telefono",
        "cliente__nombre",
        "distrito_origen",
        "distrito_destino",
        "lista_objetos",
        "nota_interna",
    )
    autocomplete_fields = ("cliente", "vendedor_asignado")
    readonly_fields = (
        "fecha_creacion",
        "fecha_ultimo_seguimiento",
        "fecha_cierre",
        "conversacion_reciente",
    )
    actions = (
        "asignarme",
        "marcar_seguimiento",
        "marcar_cotizado",
        "marcar_cerrado",
        "marcar_perdido",
        "subir_prioridad",
    )
    fieldsets = (
        (
            "Cliente",
            {
                "fields": (
                    "cliente",
                    "vendedor_asignado",
                    "estado",
                    "etapa_conversacion",
                    "prioridad",
                    "atencion_humana",
                    "requiere_asesor",
                    "bot_pausado",
                    "motivo_derivacion",
                    "fecha_derivacion",
                )
            },
        ),
        (
            "Servicio",
            {
                "fields": (
                    "tipo_servicio",
                    ("distrito_origen", "distrito_destino"),
                    ("piso_origen", "piso_destino"),
                    ("ascensor_origen", "ascensor_destino"),
                    ("camion_llega_origen", "camion_llega_destino"),
                    ("acceso_origen", "acceso_destino"),
                    ("distancia_carga_origen_m", "distancia_carga_destino_m"),
                    "lista_objetos",
                    "objetos_pesados",
                    ("incluye_personal_carga", "modalidad_servicio"),
                    "requiere_desarmado",
                    ("peso_carga_kg", "volumen_carga_m3"),
                    ("tipo_camion", "capacidad_camion"),
                )
            },
        ),
        (
            "Reserva",
            {
                "fields": (
                    "dni_reserva",
                    ("direccion_origen", "direccion_destino"),
                    ("fecha_servicio", "horario_servicio"),
                )
            },
        ),
        (
            "Precios",
            {
                "fields": (
                    ("precio_estimado_min", "precio_estimado_max", "precio_recomendado"),
                    ("precio_cotizado", "precio_final"),
                )
            },
        ),
        (
            "Gestion comercial",
            {
                "fields": (
                    "observaciones",
                    "nota_interna",
                    "motivo_perdida",
                    "fecha_ultimo_seguimiento",
                    "fecha_proximo_seguimiento",
                    "fecha_cierre",
                    "fecha_creacion",
                )
            },
        ),
        ("Conversacion", {"fields": ("conversacion_reciente",)}),
    )

    @admin.display(description="Telefono", ordering="cliente__telefono")
    def telefono(self, obj):
        return obj.cliente.telefono

    @admin.display(description="Ruta")
    def ruta(self, obj):
        return f"{obj.distrito_origen or '-'} -> {obj.distrito_destino or '-'}"

    @admin.display(description="Conversacion reciente")
    def conversacion_reciente(self, obj):
        conversaciones = obj.cliente.conversaciones.order_by("-fecha")[:8]
        if not conversaciones:
            return "Sin mensajes registrados."
        return format_html_join(
            "",
            "<div style='margin-bottom:10px; border-bottom:1px solid #ddd; padding-bottom:8px;'>"
            "<strong>{}</strong><br>"
            "<span><b>Cliente:</b> {}</span><br>"
            "<span><b>TaxiCarga:</b> {}</span>"
            "</div>",
            (
                (
                    conversacion.fecha.strftime("%Y-%m-%d %H:%M"),
                    conversacion.mensaje_entrada or "-",
                    conversacion.mensaje_salida or "-",
                )
                for conversacion in conversaciones
            ),
        )

    @admin.action(description="Asignarme leads seleccionados")
    def asignarme(self, request, queryset):
        updated = queryset.update(vendedor_asignado=request.user, estado=Lead.ASIGNADO)
        self.message_user(request, f"{updated} lead(s) asignado(s).", messages.SUCCESS)

    @admin.action(description="Registrar seguimiento ahora")
    def marcar_seguimiento(self, request, queryset):
        updated = queryset.update(fecha_ultimo_seguimiento=timezone.now())
        self.message_user(request, f"{updated} seguimiento(s) registrado(s).", messages.SUCCESS)

    @admin.action(description="Marcar como cotizado")
    def marcar_cotizado(self, request, queryset):
        updated = queryset.update(estado=Lead.COTIZADO)
        self.message_user(request, f"{updated} lead(s) marcado(s) como cotizado(s).", messages.SUCCESS)

    @admin.action(description="Marcar como cerrado")
    def marcar_cerrado(self, request, queryset):
        updated = queryset.update(estado=Lead.CERRADO, fecha_cierre=timezone.now())
        self.message_user(request, f"{updated} lead(s) cerrado(s).", messages.SUCCESS)

    @admin.action(description="Marcar como perdido")
    def marcar_perdido(self, request, queryset):
        updated = queryset.update(estado=Lead.PERDIDO, fecha_cierre=timezone.now())
        self.message_user(request, f"{updated} lead(s) perdido(s).", messages.WARNING)

    @admin.action(description="Subir prioridad")
    def subir_prioridad(self, request, queryset):
        order = [
            Lead.PRIORIDAD_BAJA,
            Lead.PRIORIDAD_MEDIA,
            Lead.PRIORIDAD_ALTA,
            Lead.PRIORIDAD_URGENTE,
        ]
        updated = 0
        for lead in queryset:
            current_index = order.index(lead.prioridad)
            lead.prioridad = order[min(current_index + 1, len(order) - 1)]
            lead.save(update_fields=["prioridad"])
            updated += 1
        self.message_user(request, f"{updated} prioridad(es) actualizada(s).", messages.SUCCESS)
