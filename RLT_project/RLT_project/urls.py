from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve
from pathlib import Path


import urllib.parse

def serve_media_fallback(request, path):
    clean_path = urllib.parse.unquote(path).lstrip('/')
    cand1 = Path(settings.MEDIA_ROOT) / clean_path
    if cand1.exists():
        return serve(request, clean_path, document_root=settings.MEDIA_ROOT)
    alt_root = Path(settings.BASE_DIR).parent / 'dataset' / 'knowledgebase_mos_ru' / 'media'
    if (alt_root / clean_path).exists():
        return serve(request, clean_path, document_root=alt_root)
    alt_root2 = Path(settings.BASE_DIR).parent / 'media'
    if (alt_root2 / clean_path).exists():
        return serve(request, clean_path, document_root=alt_root2)
    return serve(request, clean_path, document_root=settings.MEDIA_ROOT)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('chat.urls')),
    path('api/', include('rag.urls')),
    re_path(r'^media/(?P<path>.*)$', serve_media_fallback),
]
