"""Paginación estándar de la API v2.

Query params: ?page=1&pageSize=20  (pageSize máximo 100).
Respuesta:    {results: [...], page, pageSize, total, pages}
"""
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "pageSize"
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response({
            "results": data,
            "page": self.page.number,
            "pageSize": self.get_page_size(self.request),
            "total": self.page.paginator.count,
            "pages": self.page.paginator.num_pages,
        })
