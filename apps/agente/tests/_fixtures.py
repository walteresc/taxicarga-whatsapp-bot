"""Mundo mínimo para probar capacidades: 2 clientes, 1 transportista, asesor y
gerente, una carga con cotización/negociación/servicio, y una publicación."""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from apps.catalogo.models import TipoVehiculo
from apps.clientes.models import Cliente, ClienteUsuario
from apps.cotizador.commercial import crear_cotizacion_portal
from apps.leads.models import Lead
from apps.leads.route import replace_lead_route
from apps.servicios.models import Servicio
from apps.tercerizacion import adjudicacion as adj
from apps.tercerizacion import negociacion as neg
from apps.tercerizacion.models import HiloNegociacion, PublicacionCarga, Transportista, TransportistaVehiculo

from apps.agente.principal import principal_desde_usuario

User = get_user_model()


class Mundo:
    def __init__(self):
        for g in ["Asesor de Ventas", "Gerencia", "Despacho", "Finanzas", "Transportista", "Cliente Portal"]:
            Group.objects.get_or_create(name=g)

        self.u_asesor = User.objects.create_user("f_asesor", password="x")
        self.u_asesor.groups.add(Group.objects.get(name="Asesor de Ventas"))
        self.u_gerente = User.objects.create_user("f_gerente", password="x")
        self.u_gerente.groups.add(Group.objects.get(name="Gerencia"))
        self.u_despacho = User.objects.create_user("f_despacho", password="x")
        self.u_despacho.groups.add(Group.objects.get(name="Despacho"), Group.objects.get(name="Gerencia"))

        self.cliente = Cliente.objects.create(nombre="Cliente Uno", telefono="+51900000101", correo="c1@x.com")
        self.u_cliente = User.objects.create_user("f_cliente", password="x")
        self.cu = ClienteUsuario.objects.create(usuario=self.u_cliente, cliente=self.cliente)

        self.cliente2 = Cliente.objects.create(nombre="Cliente Dos", telefono="+51900000102")
        self.u_cliente2 = User.objects.create_user("f_cliente2", password="x")
        ClienteUsuario.objects.create(usuario=self.u_cliente2, cliente=self.cliente2)

        self.carrier = Transportista.objects.create(nombre="Transportes F")
        self.u_carrier = User.objects.create_user("f_carrier", password="x")
        self.carrier.usuario = self.u_carrier
        self.carrier.save()
        self.tv = TransportistaVehiculo.objects.create(
            transportista=self.carrier, placa="FFF-100",
            tipo_vehiculo=TipoVehiculo.objects.get(codigo="camion"),
        )
        self.carrier2 = Transportista.objects.create(nombre="Transportes G")
        self.u_carrier2 = User.objects.create_user("f_carrier2", password="x")
        self.carrier2.usuario = self.u_carrier2
        self.carrier2.save()

        # --- carga 1: cliente, cotizada, en negociación de venta ---
        self.lead = Lead.objects.create(
            cliente=self.cliente, tipo_servicio="mudanza", origen_carga="portal_cliente",
            distrito_origen="Miraflores", distrito_destino="Surco",
            direccion_origen="Av. Larco 100", direccion_destino="Av. Primavera 500",
            fecha_servicio=date.today() + timedelta(days=4), horario_servicio="09:00",
        )
        replace_lead_route(self.lead, [
            {"tipo": "origen", "distrito": "Miraflores", "direccion": "Av. Larco 100"},
            {"tipo": "destino", "distrito": "Surco", "direccion": "Av. Primavera 500"},
        ])
        self.cotizacion = crear_cotizacion_portal(self.lead, 900, en_negociacion=True)
        self.cotizacion.precio_cliente = 800
        self.cotizacion.save(update_fields=["precio_cliente"])
        self.hilo_venta, _ = neg.abrir_hilo(
            self.lead, HiloNegociacion.TIPO_VENTA, usuario=self.u_asesor,
            cotizacion=self.cotizacion, contraparte=self.cliente, monto_objetivo=900,
        )
        neg.publicar_mensaje(self.hilo_venta, emisor="cliente", autor=self.u_cliente, propuesta_monto=800)

        # --- carga 2: cliente2, con servicio tercerizado + publicación + oferta del carrier ---
        self.lead2 = Lead.objects.create(
            cliente=self.cliente2, tipo_servicio="carga", origen_carga="asesor_crm",
            distrito_origen="Lima", distrito_destino="Callao",
            direccion_origen="Jr. X 1", direccion_destino="Jr. Y 2",
            fecha_servicio=date.today() + timedelta(days=3), horario_servicio="08:00",
        )
        replace_lead_route(self.lead2, [
            {"tipo": "origen", "distrito": "Lima", "direccion": "Jr. X 1"},
            {"tipo": "destino", "distrito": "Callao", "direccion": "Jr. Y 2"},
        ])
        self.servicio2 = Servicio.objects.create(
            lead_origen=self.lead2, cliente=self.cliente2, tipo_servicio="carga",
            distrito_origen="Lima", distrito_destino="Callao", horario_servicio="08:00",
            fecha_servicio=self.lead2.fecha_servicio, precio=1200,
            modalidad_ejecucion=Servicio.MODALIDAD_TERCERIZADO,
        )
        self.publicacion = PublicacionCarga.objects.create(
            servicio=self.servicio2, codigo="F01", texto_publicado="OFERTA-F",
            estado=PublicacionCarga.ESTADO_ABIERTA,
            modo_precio=PublicacionCarga.PRECIO_REFERENCIAL, precio_publicado=900,
        )
        self.oferta, self.hilo_compra = adj.registrar_oferta(
            self.publicacion, monto=850, usuario=self.u_despacho, transportista=self.carrier,
        )

    # --- principals ---
    @property
    def p_asesor(self): return principal_desde_usuario(self.u_asesor)
    @property
    def p_gerente(self): return principal_desde_usuario(self.u_gerente)
    @property
    def p_despacho(self): return principal_desde_usuario(self.u_despacho)
    @property
    def p_cliente(self): return principal_desde_usuario(self.u_cliente)
    @property
    def p_cliente2(self): return principal_desde_usuario(self.u_cliente2)
    @property
    def p_carrier(self): return principal_desde_usuario(self.u_carrier)
    @property
    def p_carrier2(self): return principal_desde_usuario(self.u_carrier2)
