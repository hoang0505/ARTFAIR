from django.urls import path
from .views import (
    CategoryListView,
    TagListView,
    PublicArtworkListView,
    PublicArtworkDetailView,
    CreatorArtworkListCreateView,
    CreatorArtworkDetailView,
    ArtworkPublishView,
    ArtworkArchiveView,
    CreatorArtworkLicenseView,
    CreatorArtworkFileUploadView,
    ArtworkFileDownloadView,
    CreateOrderView,
    SimulatePaymentView,
    MyOrdersListView,
    OrderDetailView,
    CreatorStudioWizardPublishView,
    CreatorStudioWizardEditView,
    MyLibraryListView,
    OrderCertificatePDFView,
    CreatorDashboardAPIView,
    CreatorWithdrawalCreateView,
    ArtworkFavoriteToggleView,
    MyFavoritesListView,
    MyFavoriteIdsView,
)

app_name = 'artworks'

urlpatterns = [
    # Public taxonomy endpoints
    path('categories/', CategoryListView.as_view(), name='category_list'),
    path('tags/', TagListView.as_view(), name='tag_list'),

    # Favorites / Wishlist endpoints
    path('favorites/ids/', MyFavoriteIdsView.as_view(), name='my_favorite_ids'),
    path('favorites/my-favorites/', MyFavoritesListView.as_view(), name='my_favorites_list'),
    path('<str:pk>/favorite/', ArtworkFavoriteToggleView.as_view(), name='artwork_favorite_toggle'),

    # Personal Library & Certificate (Screen 04)
    path('library/my-library/', MyLibraryListView.as_view(), name='my_library_list'),
    path('orders/<str:order_code>/certificate/', OrderCertificatePDFView.as_view(), name='order_certificate_pdf'),

    # Creator Dashboard Financials & Simulated Withdrawals (Screen 04)
    path('creator/dashboard-metrics/', CreatorDashboardAPIView.as_view(), name='creator_dashboard_metrics'),
    path('creator/withdrawals/', CreatorWithdrawalCreateView.as_view(), name='creator_withdrawals'),

    # Order & payment endpoints (Screen 02 & Screen 04)
    path('orders/', CreateOrderView.as_view(), name='order_create'),
    path('orders/my-orders/', MyOrdersListView.as_view(), name='my_orders_list'),
    path('orders/<str:order_code>/', OrderDetailView.as_view(), name='order_detail'),
    path('orders/<str:order_code>/simulate-payment/', SimulatePaymentView.as_view(), name='order_simulate_payment'),

    # Secure original file download endpoint (Creator owner, Staff & Buyer with completed order)
    path('<str:artwork_id>/download-file/', ArtworkFileDownloadView.as_view(), name='artwork_download_file'),

    # Creator studio / management endpoints
    path('my-artworks/', CreatorArtworkListCreateView.as_view(), name='creator_artwork_list_create'),
    path('my-artworks/publish-wizard/', CreatorStudioWizardPublishView.as_view(), name='creator_studio_publish_wizard'),
    path('my-artworks/<int:pk>/', CreatorArtworkDetailView.as_view(), name='creator_artwork_detail'),
    path('my-artworks/<int:pk>/edit-wizard/', CreatorStudioWizardEditView.as_view(), name='creator_studio_edit_wizard'),
    path('my-artworks/<int:pk>/publish/', ArtworkPublishView.as_view(), name='creator_artwork_publish'),
    path('my-artworks/<int:pk>/archive/', ArtworkArchiveView.as_view(), name='creator_artwork_archive'),
    path('my-artworks/<int:artwork_id>/licenses/', CreatorArtworkLicenseView.as_view(), name='creator_artwork_licenses'),
    path('my-artworks/<int:artwork_id>/original-file/', CreatorArtworkFileUploadView.as_view(), name='creator_artwork_file_upload'),

    # Public catalog endpoints (list and lookup)
    path('', PublicArtworkListView.as_view(), name='public_artwork_list'),
    path('<str:lookup>/', PublicArtworkDetailView.as_view(), name='public_artwork_detail'),
]
