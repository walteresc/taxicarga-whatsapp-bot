from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.http import JsonResponse


def live(request):
    return JsonResponse({"status": "ok", "service": "taxicarga-web"})


def ready(request):
    try:
        connection.ensure_connection()
        executor = MigrationExecutor(connection)
        pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
    except Exception:
        return JsonResponse({"status": "unavailable", "database": "unavailable"}, status=503)
    if pending:
        return JsonResponse({"status": "unavailable", "database": "ok", "migrations": "pending"}, status=503)
    return JsonResponse({"status": "ok", "database": "ok", "migrations": "current"})
