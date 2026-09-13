from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve
from pathlib import Path


def serve_media_fallback(request, path):
    cand1 = Path(settings.MEDIA_ROOT) / path
    if cand1.exists():
        return serve(request, path, document_root=settings.MEDIA_ROOT)
    alt_root = Path(settings.BASE_DIR).parent / 'dataset' / 'knowledgebase_mos_ru' / 'media'
    if (alt_root / path).exists():
        return serve(request, path, document_root=alt_root)
    return serve(request, path, document_root=settings.MEDIA_ROOT)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('chat.urls')),
    path('api/', include('rag.urls')),
    re_path(r'^media/(?P<path>.*)$', serve_media_fallback),
]
