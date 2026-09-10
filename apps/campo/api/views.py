"""Viewsets de la API v2 para Personal. Finos: permisos + serializer + servicio.

Endpoints (montados en /api/v2/):
    GET/POST         /drivers/            /assistants/
    GET/PATCH/DELETE /drivers/{id}/       /assistants/{id}/
    POST             /drivers/{id}/toggle-active/   (atajo de activar/desactivar)

Lista: ?search=&status=active|inactive&ordering=name|-licenseExpiresOn&page=&pageSize=
Respuesta y errores: formato estándar de apps.api (ver docs/PATRON-API-VUE.md).
"""
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.api.permissions import HasAnyRole
from apps.api.views import V2ModelViewSet
from apps.campo.services import assistants_queryset, drivers_queryset

from .serializers import AssistantSerializer, DriverSerializer

_ROLES = ("Administrador", "Supervisor", "Asesor de Ventas")


class _PersonnelViewSet(V2ModelViewSet):
    permission_classes = [HasAnyRole(*_ROLES)]

    def get_queryset(self):
        return self._queryset_fn(self.request.query_params)

    @action(detail=True, methods=["post"], url_path="toggle-active")
    def toggle_active(self, request, pk=None):
        obj = self.get_object()
        obj.activo = not obj.activo
        obj.save(update_fields=["activo"])
        return Response(self.get_serializer(obj).data)


class DriverViewSet(_PersonnelViewSet):
    serializer_class = DriverSerializer
    _queryset_fn = staticmethod(drivers_queryset)


class AssistantViewSet(_PersonnelViewSet):
    serializer_class = AssistantSerializer
    _queryset_fn = staticmethod(assistants_queryset)


from rest_framework.views import APIView  # noqa: E402
from django.db import models  # noqa: E402
from django.shortcuts import get_object_or_404  # noqa: E402

from apps.api.exceptions import api_exception_handler  # noqa: E402


class PersonnelDirectoryView(APIView):
    """Directorio unificado de personal propio: conductores + ayudantes + asesores.
    Solo lectura. Filtros: ?type=conductor|ayudante|asesor  ?status=active|inactive
    ?search=  ?page=&pageSize=. El alta/edición sigue por cada recurso específico."""
    permission_classes = [HasAnyRole(*_ROLES)]

    def get_exception_handler(self):
        return api_exception_handler

    def get(self, request):
        from django.contrib.auth import get_user_model

        from apps.api.pagination import StandardPagination
        from apps.campo.models import Ayudante, Conductor

        tipo = (request.query_params.get("type") or "").strip().lower()
        status = (request.query_params.get("status") or "").strip().lower()
        term = (request.query_params.get("search") or "").strip().lower()

        rows = []
        if tipo in ("", "conductor"):
            for c in Conductor.objects.all():
                rows.append({
                    "id": f"c{c.id}", "sourceId": c.id, "type": "conductor",
                    "name": c.nombre, "documentId": c.dni, "phone": c.telefono,
                    "detail": (f"Lic. {c.numero_licencia}" if c.numero_licencia else ""),
                    "active": c.activo,
                })
        if tipo in ("", "ayudante"):
            for a in Ayudante.objects.all():
                rows.append({
                    "id": f"a{a.id}", "sourceId": a.id, "type": "ayudante",
                    "name": a.nombre, "documentId": a.dni, "phone": a.telefono,
                    "detail": "", "active": a.activo,
                })
        if tipo in ("", "asesor"):
            User = get_user_model()
            for u in User.objects.filter(groups__name="Asesor de Ventas").distinct():
                rows.append({
                    "id": f"u{u.id}", "sourceId": u.id, "type": "asesor",
                    "name": (u.get_full_name() or u.username), "documentId": "",
                    "phone": "", "detail": u.email, "active": u.is_active,
                })

        if status == "active":
            rows = [r for r in rows if r["active"]]
        elif status == "inactive":
            rows = [r for r in rows if not r["active"]]
        if term:
            rows = [r for r in rows if term in (r["name"] + r["documentId"] + r["phone"]).lower()]

        rows.sort(key=lambda r: r["name"].lower())

        paginator = StandardPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        return paginator.get_paginated_response(page)


class ScheduleViewSet(V2ModelViewSet):
    """Programaciones de servicio (asignación equipo↔servicio con fecha/hora).
    La creación/movimiento se hace en la Pizarra; acá solo lectura + cambio de
    estado operativo.

        GET  /api/v2/schedule/?date=YYYY-MM-DD&from=&to=&state=&search=
        POST /api/v2/schedule/{id}/set-state/  { state }
    """
    permission_classes = [HasAnyRole(*_ROLES)]
    http_method_names = ["get", "post", "head", "options"]

    def get_serializer_class(self):
        from .serializers import ScheduleSerializer
        return ScheduleSerializer

    def create(self, request, *args, **kwargs):
        from rest_framework.exceptions import MethodNotAllowed
        raise MethodNotAllowed("POST", detail="Las programaciones se crean desde la Pizarra.")

    def get_queryset(self):
        from apps.campo.models import ProgramacionServicio
        from apps.api.filters import apply_ordering, apply_search

        p = self.request.query_params
        qs = (ProgramacionServicio.objects
              .select_related(
                  "servicio", "servicio__cliente", "vehiculo", "conductor", "equipo_dia",
                  "transportista", "transportista_vehiculo",
              )
              .prefetch_related("ayudantes"))
        if p.get("date"):
            qs = qs.filter(fecha=p["date"])
        if p.get("from"):
            qs = qs.filter(fecha__gte=p["from"])
        if p.get("to"):
            qs = qs.filter(fecha__lte=p["to"])
        state = (p.get("state") or "").strip()
        if state:
            qs = qs.filter(estado_operativo=state)
        qs = apply_search(qs, p.get("search"), (
            "servicio__codigo", "servicio__cliente__nombre", "vehiculo__placa",
            "conductor__nombre", "transportista_vehiculo__placa", "conductor_externo",
        ))
        return apply_ordering(qs, p.get("ordering"),
                              {"date": "fecha", "time": "hora_inicio"}, ("fecha", "hora_inicio"))

    @action(detail=True, methods=["post"], url_path="set-state")
    def set_state(self, request, pk=None):
        from apps.campo.models import ProgramacionServicio

        obj = self.get_object()
        state = (request.data.get("state") or "").strip()
        valid = {s for s, _ in ProgramacionServicio.ESTADOS_OPERATIVOS}
        if state not in valid:
            return Response({"error": "Estado no válido."}, status=400)
        obj.estado_operativo = state
        obj.save(update_fields=["estado_operativo"])
        return Response(self.get_serializer(obj).data)


class PizarraView(APIView):
    """Tablero visual del día: recursos (vehículos propios), servicios asignados
    (ProgramacionServicio) y servicios de ese día todavía sin asignar.

        GET /api/v2/pizarra/?date=YYYY-MM-DD
    """
    permission_classes = [HasAnyRole(*_ROLES)]

    def get_exception_handler(self):
        return api_exception_handler

    def get(self, request):
        from datetime import date as _date

        from django.utils import timezone

        from apps.campo.models import ProgramacionServicio, Vehiculo
        from apps.servicios.models import Servicio
        from apps.servicios.utils import parse_horario

        raw = (request.query_params.get("date") or "").strip()
        try:
            day = _date.fromisoformat(raw) if raw else timezone.localdate()
        except ValueError:
            day = timezone.localdate()

        from apps.campo.models import FilaPizarraTransportista
        from apps.tercerizacion.models import TransportistaVehiculo

        progs = list(
            ProgramacionServicio.objects
            .filter(fecha=day).exclude(estado_operativo="cancelado")
            .select_related(
                "servicio", "servicio__cliente", "servicio__lead_origen", "vehiculo", "conductor",
                "transportista_vehiculo", "transportista_vehiculo__transportista", "transportista",
            )
            .prefetch_related("ayudantes")
        )

        # Recursos propios = vehículos activos + los que tengan una programación ese día.
        veh_ids = {p.vehiculo_id for p in progs if p.vehiculo_id}
        vehiculos = list(
            Vehiculo.objects.filter(models.Q(activo=True) | models.Q(id__in=veh_ids))
            .order_by("placa")
        )
        # conductor "típico" del vehículo ese día (el de su última programación)
        driver_by_veh = {}
        for p in sorted(progs, key=lambda x: x.hora_inicio):
            if p.vehiculo_id and p.conductor_id:
                driver_by_veh[p.vehiculo_id] = (p.conductor_id, p.conductor.nombre)

        resources = [
            {
                "id": f"v{v.id}", "kind": "propio", "vehicleId": v.id, "carrierVehicleId": None,
                "label": f"{v.placa}", "sublabel": f"{v.marca} {v.modelo}".strip(),
                "driverId": driver_by_veh.get(v.id, (None, None))[0],
                "driverName": driver_by_veh.get(v.id, (None, None))[1],
            }
            for v in vehiculos
        ]

        # Recursos de transportistas = filas agregadas ese día + los que tengan programación.
        filas = list(FilaPizarraTransportista.objects.filter(fecha=day))
        tv_ids = {p.transportista_vehiculo_id for p in progs if p.transportista_vehiculo_id}
        tv_ids |= {f.transportista_vehiculo_id for f in filas}
        driver_txt_by_tv = {f.transportista_vehiculo_id: f.conductor_externo for f in filas}
        for p in sorted(progs, key=lambda x: x.hora_inicio):
            if p.transportista_vehiculo_id and p.conductor_externo:
                driver_txt_by_tv[p.transportista_vehiculo_id] = p.conductor_externo
        if tv_ids:
            for tv in (TransportistaVehiculo.objects
                       .filter(id__in=tv_ids).select_related("transportista").order_by("placa")):
                sub = " · ".join(filter(None, [
                    f"{tv.marca} {tv.modelo}".strip(), tv.transportista.nombre,
                ]))
                resources.append({
                    "id": f"t{tv.id}", "kind": "tercerizado",
                    "vehicleId": None, "carrierVehicleId": tv.id, "carrierId": tv.transportista_id,
                    "label": tv.placa, "sublabel": sub,
                    "driverId": None, "driverName": driver_txt_by_tv.get(tv.id) or None,
                })

        def _hhmm(t):
            return t.strftime("%H:%M") if t else None

        def _res_id(p):
            if p.vehiculo_id:
                return f"v{p.vehiculo_id}"
            if p.transportista_vehiculo_id:
                return f"t{p.transportista_vehiculo_id}"
            return None

        assignments = []
        for p in progs:
            s = p.servicio
            assignments.append({
                "id": p.id,
                "resourceId": _res_id(p),
                "serviceId": s.id if s else None,
                "leadId": s.lead_origen_id if s else None,
                "serviceCode": s.codigo if s else "—",
                "customer": (s.cliente.nombre or s.cliente.profile_name) if s and s.cliente else "Sin cliente",
                "originDistrict": s.distrito_origen if s else "",
                "destDistrict": s.distrito_destino if s else "",
                "route": f"{s.distrito_origen or '?'} → {s.distrito_destino or '?'}" if s else "",
                "start": _hhmm(p.hora_inicio),
                "end": _hhmm(p.hora_fin),
                "state": p.estado_operativo,
                "price": float(p.monto) if p.monto is not None else None,
                "mode": s.modalidad_ejecucion if s else "propio",
                "assignedAuto": p.origen_asignacion == "auto",
                "driverName": p.conductor.nombre if p.conductor_id else (p.conductor_externo or None),
                "helpers": [a.nombre for a in p.ayudantes.all()],
            })

        asignados_ids = {p.servicio_id for p in progs}
        sin_asignar = (
            Servicio.objects
            .filter(fecha_servicio=day)
            .exclude(id__in=asignados_ids)
            .exclude(estado__in=("finalizado", "cancelado"))
            .select_related("cliente", "lead_origen")
        )
        unassigned = []
        for s in sin_asignar:
            publicado = s.publicaciones_tercerizacion.filter(estado="abierta").exists()
            unassigned.append({
                "serviceId": s.id,
                "leadId": s.lead_origen_id,
                "serviceCode": s.codigo,
                "customer": (s.cliente.nombre or s.cliente.profile_name) if s.cliente else "Sin cliente",
                "originDistrict": s.distrito_origen or "",
                "destDistrict": s.distrito_destino or "",
                "route": f"{s.distrito_origen or '?'} → {s.distrito_destino or '?'}",
                "start": _hhmm(parse_horario(s.horario_servicio)),
                "scheduleText": s.horario_servicio or "",
                "mode": s.modalidad_ejecucion,
                "published": publicado,
                "price": float(s.precio) if s.precio is not None else None,
            })

        return Response({
            "date": day.isoformat(),
            "resources": resources,
            "assignments": assignments,
            "unassigned": unassigned,
        })


# La lógica de Pizarra (resolver recurso, conflictos, asignar/mover) vive en
# apps/campo/services.py — compartida con el catálogo de capacidades del agente.
from apps.campo.services import (  # noqa: E402
    PizarraError, asignar_servicio, desasignar, mover_programacion,
)
from apps.campo.services import es_tv as _es_tv  # noqa: E402
from apps.campo.services import hay_conflicto as _pizarra_conflicto  # noqa: E402
from apps.campo.services import resolver_recurso as _pizarra_resource  # noqa: E402


class PizarraMutationView(APIView):
    """Acciones de la Pizarra sin recargar:
      POST /api/v2/pizarra/assign             {serviceId, resourceId, start, end?, driverId?, externalDriverName?}
      POST /api/v2/pizarra/move               {assignmentId, resourceId, start}
      POST /api/v2/pizarra/unassign           {assignmentId}
      POST /api/v2/pizarra/edit               {assignmentId, driverId?|externalDriverName?, helperIds?, start?, end?, state?}
      POST /api/v2/pizarra/add-carrier-row    {date, carrierVehicleId, driverName?}
      POST /api/v2/pizarra/remove-carrier-row {date, resourceId}

    resourceId = 'v<id>' (vehículo propio) | 't<id>' (vehículo de transportista).
    """
    permission_classes = [HasAnyRole("Administrador", "Supervisor", "Asesor de Ventas")]

    def get_exception_handler(self):
        return api_exception_handler

    def post(self, request, action):
        from datetime import date as _date
        from datetime import datetime, timedelta

        from apps.campo.models import (
            Ayudante, Conductor, FilaPizarraTransportista, ProgramacionServicio,
        )
        from apps.servicios.models import Servicio
        from apps.servicios.utils import parse_horario

        d = request.data

        def _time(v):
            try:
                return datetime.strptime(v, "%H:%M").time()
            except (ValueError, TypeError):
                return None

        def _parse_date(v):
            try:
                return _date.fromisoformat((v or "").strip())
            except ValueError:
                return None

        if action == "add-carrier-row":
            from apps.tercerizacion.models import TransportistaVehiculo
            fecha = _parse_date(d.get("date"))
            if not fecha:
                return Response({"error": "Fecha inválida."}, status=400)
            tv = TransportistaVehiculo.objects.filter(pk=d.get("carrierVehicleId")).first()
            if not tv:
                return Response({"error": "Vehículo de transportista no encontrado."}, status=404)
            fila, _ = FilaPizarraTransportista.objects.get_or_create(
                fecha=fecha, transportista_vehiculo=tv,
                defaults={"creado_por": request.user if request.user.is_authenticated else None},
            )
            nombre = (d.get("driverName") or "").strip()
            if nombre and nombre != fila.conductor_externo:
                fila.conductor_externo = nombre
                fila.save(update_fields=["conductor_externo"])
            return Response({"ok": True, "resourceId": f"t{tv.id}"})

        if action == "remove-carrier-row":
            fecha = _parse_date(d.get("date"))
            rid = d.get("resourceId") or ""
            if not fecha or not rid.startswith("t"):
                return Response({"error": "Datos inválidos."}, status=400)
            try:
                tv_id = int(rid[1:])
            except ValueError:
                return Response({"error": "Datos inválidos."}, status=400)
            if ProgramacionServicio.objects.filter(
                fecha=fecha, transportista_vehiculo_id=tv_id,
            ).exclude(estado_operativo="cancelado").exists():
                return Response(
                    {"error": "Esta fila tiene servicios asignados. Quitá las asignaciones primero."},
                    status=409,
                )
            FilaPizarraTransportista.objects.filter(
                fecha=fecha, transportista_vehiculo_id=tv_id,
            ).delete()
            return Response({"ok": True})

        if action == "unassign":
            ps = get_object_or_404(ProgramacionServicio, pk=d.get("assignmentId"))
            desasignar(ps)
            return Response({"ok": True})

        if action == "assign":
            servicio = get_object_or_404(Servicio, pk=d.get("serviceId"))
            recurso = _pizarra_resource(d.get("resourceId"))
            if not recurso:
                return Response({"error": "Vehículo no encontrado."}, status=404)
            conductor = None
            if d.get("driverId") and not _es_tv(recurso):
                conductor = Conductor.objects.filter(pk=d["driverId"]).first()
            try:
                ps = asignar_servicio(
                    servicio, recurso,
                    hora_inicio=_time(d.get("start")), hora_fin=_time(d.get("end")),
                    conductor=conductor, conductor_externo=d.get("externalDriverName") or "",
                    actor=request.user,
                )
            except PizarraError as e:
                return Response({"error": str(e)}, status=e.status)
            return Response({"ok": True, "id": ps.id})

        ps = get_object_or_404(ProgramacionServicio.objects.select_related("servicio"), pk=d.get("assignmentId"))

        if action == "move":
            destino = _pizarra_resource(d.get("resourceId"))
            try:
                mover_programacion(ps, destino, hora_inicio=_time(d.get("start")), actor=request.user)
            except PizarraError as e:
                return Response({"error": str(e)}, status=e.status)
            return Response({"ok": True})

        if action == "edit":
            fields = []
            es_terc = ps.transportista_vehiculo_id is not None
            if es_terc and "externalDriverName" in d:
                ps.conductor_externo = (d.get("externalDriverName") or "").strip()
                fields.append("conductor_externo")
            if not es_terc and "driverId" in d:
                ps.conductor = Conductor.objects.filter(pk=d["driverId"]).first()
                fields.append("conductor")
            if "start" in d and _time(d["start"]):
                ps.hora_inicio = _time(d["start"])
                fields.append("hora_inicio")
            if "end" in d:
                ps.hora_fin = _time(d["end"])
                fields.append("hora_fin")
            if "state" in d and d["state"] in {s for s, _ in ProgramacionServicio.ESTADOS_OPERATIVOS}:
                ps.estado_operativo = d["state"]
                fields.append("estado_operativo")
            if fields:
                ps.save(update_fields=fields)
            if not es_terc and "helperIds" in d:
                ps.ayudantes.set(Ayudante.objects.filter(pk__in=d["helperIds"] or []))
            return Response({"ok": True})

        return Response({"error": "Acción desconocida."}, status=400)
