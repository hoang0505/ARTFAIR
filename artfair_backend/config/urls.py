from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from .views import (
    home_view,
    artwork_detail_view,
    creator_studio_view,
    user_dashboard_view,
    artists_list_view,
    collections_list_view,
    collection_detail_view,
    about_view,
    help_view,
    settings_view,
    terms_view,
    privacy_view,
    api_root_overview,
    custom_404_view,
    custom_403_view
)
from commissions.views import artist_profile_page_view, commission_detail_page_view

urlpatterns = [
    path('', home_view, name='home'),
    path('artworks/<slug:slug>/', artwork_detail_view, name='artwork_detail'),
    path('studio/', creator_studio_view, name='creator_studio'),
    path('dashboard/', user_dashboard_view, name='user_dashboard'),
    path('artists/', artists_list_view, name='artist_list'),
    path('artists/<str:username>/', artist_profile_page_view, name='artist_profile'),
    path('collections/', collections_list_view, name='collections_list'),
    path('collections/<slug:slug>/', collection_detail_view, name='collection_detail'),
    path('about/', about_view, name='about'),
    path('help/', help_view, name='help'),
    path('settings/', settings_view, name='settings'),
    path('terms/', terms_view, name='terms'),
    path('privacy/', privacy_view, name='privacy'),
    path('commissions/<int:pk>/', commission_detail_page_view, name='commission_detail'),
    path('api/', api_root_overview, name='api_root'),
    path('admin/', admin.site.urls),
    path('api/accounts/', include('accounts.urls', namespace='accounts')),
    path('api/artworks/', include('artworks.urls', namespace='artworks')),
    path('api/commissions/', include('commissions.urls', namespace='commissions')),
]

handler404 = 'config.views.custom_404_view'
handler403 = 'config.views.custom_403_view'

# In development: serve public previews and avatars through MEDIA_URL.
# NOTE: settings.PROTECTED_MEDIA_ROOT is intentionally NOT included here!
# Original delivery files are served exclusively through /api/artworks/<id>/download-file/
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
