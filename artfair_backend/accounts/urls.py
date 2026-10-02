from django.urls import path
from .views import (
    CSRFTokenView,
    RegisterView,
    LoginView,
    LogoutView,
    UserMeView,
    ArtistProfileView,
    PublicArtistProfileView,
    NotificationListView,
    NotificationMarkReadView,
    NotificationMarkAllReadView,
    ArtistReviewsByUsernameView,
    ArtistReviewCreateUpdateView,
)

app_name = 'accounts'

urlpatterns = [
    # Auth endpoints
    path('auth/csrf/', CSRFTokenView.as_view(), name='csrf_token'),
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/logout/', LogoutView.as_view(), name='logout'),

    # Profile endpoints
    path('me/', UserMeView.as_view(), name='user_me'),
    path('artist-profile/', ArtistProfileView.as_view(), name='creator_artist_profile'),
    path('artists/<str:username>/', PublicArtistProfileView.as_view(), name='public_artist_profile'),

    # Notifications endpoints
    path('notifications/', NotificationListView.as_view(), name='notifications_list'),
    path('notifications/<int:pk>/read/', NotificationMarkReadView.as_view(), name='notification_mark_read'),
    path('notifications/mark-all-read/', NotificationMarkAllReadView.as_view(), name='notification_mark_all_read'),

    # Artist Reviews & Rating endpoints
    path('artists/<str:username>/reviews/', ArtistReviewsByUsernameView.as_view(), name='artist_reviews_list'),
    path('reviews/', ArtistReviewCreateUpdateView.as_view(), name='artist_review_create_update'),
]

