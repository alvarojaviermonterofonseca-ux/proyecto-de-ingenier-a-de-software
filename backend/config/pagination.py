"""Paginación común de la API."""

from rest_framework.pagination import PageNumberPagination


class PaginacionApi(PageNumberPagination):
    """Permite que el cliente elija el tamaño de página con ``?page_size=``."""

    page_size_query_param = "page_size"
    max_page_size = 200
