"""URL configuration for config project."""

from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView, TemplateView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from config.frontend import spa_view


urlpatterns = [
    path('panel/', TemplateView.as_view(template_name='panel.html'), name='frontend-panel'),
    path('app/', spa_view, name='frontend-app'),
    path('app/<path:path>', spa_view, name='frontend-app-route'),
    path('', RedirectView.as_view(url='/api/v1/', permanent=False), name='root'),
    path('admin/', admin.site.urls),
    path('api/v1/schema/', SpectacularAPIView.as_view(), name='schema-v1'),
    path(
        'api/v1/docs/',
        SpectacularSwaggerView.as_view(url_name='schema-v1'),
        name='docs-v1',
    ),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='docs'),
    path('api/v1/', include(('gym.urls', 'gym'), namespace='gym')),
    path('api/', include(('gym.urls', 'gym_legacy'), namespace='gym_legacy')),
]
