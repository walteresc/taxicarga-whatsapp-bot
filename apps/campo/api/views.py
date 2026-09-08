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
              .select_related("servicio", "servicio__cliente", "vehiculo", "conductor", "equipo_dia")
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
        qs = apply_search(qs, p.get("search"),
                          ("servicio__codigo", "servicio__cliente__nombre", "vehiculo__placa", "conductor__nombre"))
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

        progs = list(
            ProgramacionServicio.objects
            .filter(fecha=day).exclude(estado_operativo="cancelado")
            .select_related("servicio", "servicio__cliente", "servicio__lead_origen", "vehiculo", "conductor")
            .prefetch_related("ayudantes")
        )

        # Recursos = vehículos propios activos + los que tengan una programación ese día.
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
                "id": f"v{v.id}", "kind": "propio", "vehicleId": v.id,
                "label": f"{v.placa}", "sublabel": f"{v.marca} {v.modelo}".strip(),
                "driverId": driver_by_veh.get(v.id, (None, None))[0],
                "driverName": driver_by_veh.get(v.id, (None, None))[1],
            }
            for v in vehiculos
        ]

        def _hhmm(t):
            return t.strftime("%H:%M") if t else None

        assignments = []
        for p in progs:
            s = p.servicio
            assignments.append({
                "id": p.id,
                "resourceId": f"v{p.vehiculo_id}" if p.vehiculo_id else None,
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
                "driverName": p.conductor.nombre if p.conductor_id else None,
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


def _pizarra_resource(resource_id):
    """resourceId 'v<id>' → Vehiculo. (transportistas: Fase 2b)"""
    from apps.campo.models import Vehiculo
    if not resource_id or not resource_id.startswith("v"):
        return None
    try:
        return Vehiculo.objects.get(pk=int(resource_id[1:]))
    except (Vehiculo.DoesNotExist, ValueError):
        return None


def _pizarra_conflicto(vehiculo, fecha, hora_ini, hora_fin, exclude_id=None):
    from apps.campo.models import ProgramacionServicio
    qs = ProgramacionServicio.objects.filter(
        vehiculo=vehiculo, fecha=fecha,
    ).exclude(estado_operativo="cancelado")
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    qs = qs.filter(
        models.Q(hora_fin__isnull=True) | models.Q(hora_fin__gt=hora_ini),
    )
    if hora_fin:
        qs = qs.filter(hora_inicio__lt=hora_fin)
    return qs.select_related("servicio").first()


class PizarraMutationView(APIView):
    """Acciones de la Pizarra sin recargar:
      POST /api/v2/pizarra/assign     {serviceId, resourceId, start}
      POST /api/v2/pizarra/move       {assignmentId, resourceId, start}
      POST /api/v2/pizarra/unassign   {assignmentId}
      POST /api/v2/pizarra/edit       {assignmentId, driverId?, helperIds?, start?, end?, state?}
    """
    permission_classes = [HasAnyRole("Administrador", "Supervisor", "Asesor de Ventas")]

    def get_exception_handler(self):
        return api_exception_handler

    def post(self, request, action):
        from datetime import datetime, timedelta

        from apps.campo.models import Ayudante, Conductor, ProgramacionServicio
        from apps.servicios.models import Servicio
        from apps.servicios.utils import parse_horario

        d = request.data

        def _time(v):
            try:
                return datetime.strptime(v, "%H:%M").time()
            except (ValueError, TypeError):
                return None

        if action == "unassign":
            ps = get_object_or_404(ProgramacionServicio, pk=d.get("assignmentId"))
            ps.delete()
            return Response({"ok": True})

        if action == "assign":
            servicio = get_object_or_404(Servicio, pk=d.get("serviceId"))
            veh = _pizarra_resource(d.get("resourceId"))
            if not veh:
                return Response({"error": "Vehículo no encontrado."}, status=404)
            if ProgramacionServicio.objects.filter(servicio=servicio).exclude(estado_operativo="cancelado").exists():
                return Response({"error": "El servicio ya está asignado."}, status=409)
            hora_ini = _time(d.get("start")) or parse_horario(servicio.horario_servicio)
            if not servicio.fecha_servicio or not hora_ini:
                return Response({"error": "El servicio necesita fecha y hora."}, status=409)
            hora_fin = _time(d.get("end")) or (
                datetime.combine(servicio.fecha_servicio, hora_ini) + timedelta(hours=1)
            ).time()
            conductor = Conductor.objects.filter(pk=d["driverId"]).first() if d.get("driverId") else None
            c = _pizarra_conflicto(veh, servicio.fecha_servicio, hora_ini, hora_fin)
            if c:
                return Response({"error": f"Choca con {c.servicio.codigo if c.servicio else 'otra'} ({c.hora_inicio:%H:%M})"}, status=409)
            ps = ProgramacionServicio.objects.create(
                servicio=servicio, vehiculo=veh, conductor=conductor,
                fecha=servicio.fecha_servicio, hora_inicio=hora_ini, hora_fin=hora_fin,
                monto=servicio.precio or 0,
            )
            return Response({"ok": True, "id": ps.id})

        ps = get_object_or_404(ProgramacionServicio.objects.select_related("servicio"), pk=d.get("assignmentId"))

        if action == "move":
            veh = _pizarra_resource(d.get("resourceId")) or ps.vehiculo
            hora_ini = _time(d.get("start")) or ps.hora_inicio
            dur = timedelta(hours=1)
            if ps.hora_fin:
                dur = datetime.combine(ps.fecha, ps.hora_fin) - datetime.combine(ps.fecha, ps.hora_inicio)
            hora_fin = (datetime.combine(ps.fecha, hora_ini) + dur).time()
            c = _pizarra_conflicto(veh, ps.fecha, hora_ini, hora_fin, exclude_id=ps.pk)
            if c:
                return Response({"error": f"Choca con {c.servicio.codigo if c.servicio else 'otra'} ({c.hora_inicio:%H:%M})"}, status=409)
            ps.vehiculo = veh
            ps.hora_inicio = hora_ini
            ps.hora_fin = hora_fin
            ps.save(update_fields=["vehiculo", "hora_inicio", "hora_fin"])
            return Response({"ok": True})

        if action == "edit":
            fields = []
            if "driverId" in d:
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
            if "helperIds" in d:
                ps.ayudantes.set(Ayudante.objects.filter(pk__in=d["helperIds"] or []))
            return Response({"ok": True})

        return Response({"error": "Acción desconocida."}, status=400)
