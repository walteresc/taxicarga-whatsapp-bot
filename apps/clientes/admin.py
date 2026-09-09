from django.contrib import admin

from .models import Cliente, ClienteUsuario, Conversacion, Empresa


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ["razon_social", "ruc", "activo", "creado_en"]
    search_fields = ["razon_social", "ruc"]


@admin.register(ClienteUsuario)
class ClienteUsuarioAdmin(admin.ModelAdmin):
    list_display = ["usuario", "cliente", "empresa", "rol", "activo"]
    list_filter = ["rol", "activo"]
    search_fields = ["usuario__username", "cliente__nombre", "empresa__razon_social"]
    raw_id_fields = ["usuario", "cliente", "empresa"]


class ConversacionInline(admin.TabularInline):
    model = Conversacion
    extra = 0
    fields = ("fecha", "canal", "mensaje_entrada", "mensaje_salida")
    readonly_fields = ("fecha", "canal", "mensaje_entrada", "mensaje_salida")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("telefono", "nombre", "ultima_interaccion", "fecha_creacion")
    search_fields = ("telefono", "nombre")
    readonly_fields = ("fecha_creacion", "ultima_interaccion")
    inlines = (ConversacionInline,)


@admin.register(Conversacion)
class ConversacionAdmin(admin.ModelAdmin):
    list_display = ("cliente", "canal", "fecha", "resumen_entrada")
    list_filter = ("canal", "fecha")
    search_fields = ("cliente__telefono", "cliente__nombre", "mensaje_entrada", "mensaje_salida")
    readonly_fields = ("fecha",)

    @admin.display(description="Entrada")
    def resumen_entrada(self, obj):
        return obj.mensaje_entrada[:80]
