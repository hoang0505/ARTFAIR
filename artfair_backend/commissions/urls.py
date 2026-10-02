from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CommissionViewSet,
    download_reference_view,
    download_sketch_view,
    download_proposal_sketch_view,
    download_deliverable_view,
    download_commission_certificate_view
)

app_name = 'commissions'

router = DefaultRouter()
router.register(r'', CommissionViewSet, basename='commission')

urlpatterns = [
    # Protected download routes
    path('<int:pk>/download-reference/', download_reference_view, name='download_reference'),
    path('<int:pk>/download-sketch/', download_sketch_view, name='download_sketch'),
    path('<int:pk>/download-proposal-sketch/<int:proposal_id>/', download_proposal_sketch_view, name='download_proposal_sketch'),
    path('<int:pk>/download-deliverable/', download_deliverable_view, name='download_deliverable'),
    path('<int:pk>/certificate/', download_commission_certificate_view, name='certificate'),
    
    # DRF ViewSet routes
    path('', include(router.urls)),
]
