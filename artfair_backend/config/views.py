import json
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, Http404, HttpResponse
from django.core.paginator import Paginator
from django.db.models import Count, Sum, Q
from django.contrib.auth import get_user_model, update_session_auth_hash

from artworks.models import Category, Tag, Artwork, Order, LicenseOption, Withdrawal, get_creator_financials
from commissions.models import Commission

User = get_user_model()


def home_view(request):
    """
    Renders Screen 01: ARTFAIR Home & Explore page with categories, tags,
    featured artworks cluster, and featured creators.
    """
    categories = Category.objects.all().order_by('name')
    tags = Tag.objects.all().order_by('name')
    
    # 2-3 real published artworks for the hero banner visual cluster
    featured_artworks = Artwork.objects.filter(
        status=Artwork.Status.PUBLISHED
    ).select_related(
        'creator', 'creator__artist_profile', 'category'
    ).prefetch_related(
        'license_options'
    ).order_by('-created_at')[:3]
    
    # Exclude pure admin account from artist spotlight
    creators = User.objects.filter(
        role=User.Role.CREATOR,
        is_active=True
    ).exclude(
        username='admin'
    ).select_related('artist_profile').order_by('username')
    
    styles = [
        {'id': 'son-dau', 'name': 'Sơn dầu'},
        {'id': 'phuc-hung', 'name': 'Phục hưng'},
        {'id': 'toi-gian', 'name': 'Tối giản'},
        {'id': 'digital-painting', 'name': 'Digital Painting'},
        {'id': 'anime', 'name': 'Anime / Manga'},
        {'id': 'thuy-mac', 'name': 'Thủy mặc'},
        {'id': 'concept-art', 'name': 'Concept Art'},
        {'id': '3d-render', 'name': '3D Render'},
    ]
    
    return render(request, 'home.html', {
        'categories': categories,
        'tags': tags,
        'styles': styles,
        'creators': creators,
        'featured_artworks': featured_artworks,
    })


def artwork_detail_view(request, slug):
    """
    Renders Screen 02: Chi tiết tác phẩm và giao dịch mua quyền sử dụng.
    """
    artwork = get_object_or_404(
        Artwork.objects.select_related(
            'creator',
            'creator__artist_profile',
            'category',
            'original_file'
        ).prefetch_related(
            'tags',
            'license_options'
        ),
        slug=slug,
        status=Artwork.Status.PUBLISHED
    )

    license_options = artwork.license_options.filter(is_active=True).order_by('license_type')

    owned_license_types = []
    is_owner = False
    has_any_download_access = False

    if request.user.is_authenticated:
        if request.user == artwork.creator or request.user.is_staff:
            is_owner = True
            has_any_download_access = True

        completed_orders = Order.objects.filter(
            buyer=request.user,
            artwork=artwork,
            status=Order.Status.COMPLETED
        ).values_list('license_type', flat=True)
        owned_license_types = list(completed_orders)
        if owned_license_types:
            has_any_download_access = True

    original_file = getattr(artwork, 'original_file', None)

    licenses_data = [
        {
            'id': lic.id,
            'type': lic.license_type,
            'name': lic.get_license_type_display(),
            'price': int(lic.price),
            'terms': lic.terms,
            'is_owned': lic.license_type in owned_license_types,
        }
        for lic in license_options
    ]

    # Real other artworks by this creator
    other_artworks = Artwork.objects.filter(
        creator=artwork.creator,
        status=Artwork.Status.PUBLISHED
    ).exclude(
        id=artwork.id
    ).select_related('category').prefetch_related('license_options').order_by('-created_at')[:4]

    is_favorited = False
    if request.user.is_authenticated:
        from artworks.models import ArtworkFavorite
        is_favorited = ArtworkFavorite.objects.filter(user=request.user, artwork=artwork).exists()

    context = {
        'artwork': artwork,
        'license_options': license_options,
        'licenses_json': json.dumps(licenses_data),
        'owned_license_types': owned_license_types,
        'is_owner': is_owner,
        'is_favorited': is_favorited,
        'has_any_download_access': has_any_download_access,
        'original_file': original_file,
        'other_artworks': other_artworks,
    }
    return render(request, 'artwork_detail.html', context)


def creator_studio_view(request):
    """
    Renders Screen 03: Creator Studio & Publishing Hub.
    STRICT PERMISSION:
    - Guests and Buyers are forbidden from entering (HTTP 403 Forbidden).
    - Only authenticated CREATOR (or staff) can access.
    """
    if not request.user.is_authenticated:
        return render(request, 'studio_forbidden.html', {
            'reason': 'unauthenticated'
        }, status=403)

    if not request.user.is_creator and not request.user.is_staff:
        return render(request, 'studio_forbidden.html', {
            'reason': 'buyer_forbidden',
            'user': request.user
        }, status=403)

    artworks_qs = Artwork.objects.filter(
        creator=request.user
    ).select_related(
        'category'
    ).prefetch_related(
        'tags',
        'license_options'
    ).annotate(
        completed_orders_count=Count('orders', filter=Q(orders__status=Order.Status.COMPLETED))
    ).order_by('-created_at')

    categories = Category.objects.all().order_by('name')
    tags = Tag.objects.all().order_by('name')

    total_artworks = artworks_qs.count()
    published_count = artworks_qs.filter(status=Artwork.Status.PUBLISHED).count()
    draft_count = artworks_qs.filter(status=Artwork.Status.DRAFT).count()
    archived_count = artworks_qs.filter(status=Artwork.Status.ARCHIVED).count()

    total_completed_orders = Order.objects.filter(
        artwork__creator=request.user,
        status=Order.Status.COMPLETED
    ).count()

    total_revenue = Order.objects.filter(
        artwork__creator=request.user,
        status=Order.Status.COMPLETED
    ).aggregate(total=Sum('price_paid'))['total'] or Decimal('0')

    artist_profile = getattr(request.user, 'artist_profile', None)

    context = {
        'artworks': artworks_qs,
        'categories': categories,
        'tags': tags,
        'total_artworks': total_artworks,
        'published_count': published_count,
        'draft_count': draft_count,
        'archived_count': archived_count,
        'total_completed_orders': total_completed_orders,
        'total_revenue': total_revenue,
        'artist_profile': artist_profile,
    }
    return render(request, 'studio.html', context)


def user_dashboard_view(request):
    """
    Renders Screen 04: Quản lý cá nhân, kho tác phẩm đã mua, đơn hàng và dashboard nghệ sĩ.
    Requires authentication. If guest, redirects to home with login modal trigger.
    """
    if not request.user.is_authenticated:
        return redirect('/?auth=login&next=/dashboard/')

    library_orders = Order.objects.filter(
        buyer=request.user,
        status=Order.Status.COMPLETED
    ).select_related(
        'artwork',
        'artwork__creator',
        'artwork__creator__artist_profile',
        'artwork__original_file'
    ).order_by('-completed_at')

    my_orders = Order.objects.filter(
        buyer=request.user
    ).select_related(
        'artwork',
        'artwork__creator'
    ).order_by('-created_at')

    buyer_commissions = Commission.objects.filter(
        buyer=request.user
    ).select_related(
        'creator',
        'creator__artist_profile'
    ).order_by('-created_at')

    from artworks.models import ArtworkFavorite
    from accounts.models import Notification, ArtistReview

    user_favorites = ArtworkFavorite.objects.filter(
        user=request.user,
        artwork__status=Artwork.Status.PUBLISHED
    ).select_related('artwork', 'artwork__creator', 'artwork__creator__artist_profile').order_by('-created_at')

    user_notifications = Notification.objects.filter(
        recipient=request.user
    ).order_by('-created_at')[:50]

    user_reviews_given = {
        r.order_id: r for r in ArtistReview.objects.filter(reviewer=request.user, order__isnull=False)
    }
    user_comm_reviews_given = {
        r.commission_id: r for r in ArtistReview.objects.filter(reviewer=request.user, commission__isnull=False)
    }

    context = {
        'library_orders': library_orders,
        'my_orders': my_orders,
        'buyer_commissions': buyer_commissions,
        'user_favorites': user_favorites,
        'user_notifications': user_notifications,
        'user_reviews_given': user_reviews_given,
        'user_comm_reviews_given': user_comm_reviews_given,
        'user': request.user,
    }

    if request.user.is_creator or request.user.is_staff:
        financials = get_creator_financials(request.user)
        creator_artworks_count = Artwork.objects.filter(
            creator=request.user,
            status=Artwork.Status.PUBLISHED
        ).count()
        creator_sales = Order.objects.filter(
            artwork__creator=request.user,
            status=Order.Status.COMPLETED
        ).select_related('artwork', 'buyer').order_by('-completed_at')
        creator_withdrawals = Withdrawal.objects.filter(
            creator=request.user
        ).order_by('-created_at')
        creator_commissions = Commission.objects.filter(
            creator=request.user
        ).select_related('buyer').order_by('-created_at')

        context.update({
            'financials': financials,
            'creator_artworks_count': creator_artworks_count,
            'creator_sales': creator_sales,
            'creator_withdrawals': creator_withdrawals,
            'creator_commissions': creator_commissions,
            'artist_profile': getattr(request.user, 'artist_profile', None),
        })

    return render(request, 'dashboard.html', context)


# ==============================================================================
# Additional Pages Required by Menu
# ==============================================================================

def artists_list_view(request):
    """
    Renders public directory of creators / artists (/artists/).
    Supports search by name, filter accepting commissions, and pagination.
    """
    q = request.GET.get('q', '').strip()
    accepting = request.GET.get('accepting', '').strip()

    qs = User.objects.filter(
        role=User.Role.CREATOR,
        is_active=True
    ).exclude(
        username='admin'
    ).select_related('artist_profile').order_by('username')

    if q:
        qs = qs.filter(
            Q(username__icontains=q) |
            Q(artist_profile__display_name__icontains=q) |
            Q(artist_profile__bio__icontains=q)
        )

    if accepting in ['1', 'true', 'yes']:
        qs = qs.filter(artist_profile__is_accepting_commissions=True)

    # Attach published artwork count and sample artwork to each artist
    artists_data = []
    for artist in qs:
        artworks = Artwork.objects.filter(
            creator=artist,
            status=Artwork.Status.PUBLISHED
        ).order_by('-created_at')
        count = artworks.count()
        sample_art = artworks.first()
        artists_data.append({
            'artist': artist,
            'profile': getattr(artist, 'artist_profile', None),
            'artworks_count': count,
            'sample_art': sample_art,
        })

    paginator = Paginator(artists_data, 12)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    return render(request, 'artist_list.html', {
        'page_obj': page_obj,
        'q': q,
        'accepting': accepting,
        'total_artists': len(artists_data),
    })


def collections_list_view(request):
    """
    Renders public collections index (/collections/).
    Groups artworks by Category with counts and representative cover art.
    """
    categories = Category.objects.all().order_by('name')
    collections = []

    for cat in categories:
        published_artworks = Artwork.objects.filter(
            category=cat,
            status=Artwork.Status.PUBLISHED
        ).order_by('-created_at')
        count = published_artworks.count()
        cover_art = published_artworks.first()
        collections.append({
            'category': cat,
            'name': cat.name,
            'slug': cat.slug,
            'description': cat.description or f'Tuyển tập các tác phẩm nghệ thuật thuộc nhóm {cat.name} trên ARTFAIR.',
            'count': count,
            'cover_art': cover_art,
        })

    return render(request, 'collections_list.html', {
        'collections': collections,
    })


def collection_detail_view(request, slug):
    """
    Renders detail page of a collection / category (/collections/<slug>/).
    """
    category = get_object_or_404(Category, slug=slug)
    artworks_qs = Artwork.objects.filter(
        category=category,
        status=Artwork.Status.PUBLISHED
    ).select_related(
        'creator',
        'creator__artist_profile'
    ).prefetch_related(
        'license_options'
    ).order_by('-created_at')

    sort = request.GET.get('sort', '-created_at')
    if sort in ['-created_at', 'created_at', 'title']:
        artworks_qs = artworks_qs.order_by(sort)

    paginator = Paginator(artworks_qs, 12)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    return render(request, 'collection_detail.html', {
        'category': category,
        'page_obj': page_obj,
        'sort': sort,
        'total_count': artworks_qs.count(),
    })


def about_view(request):
    """
    Renders About ARTFAIR page (/about/).
    """
    return render(request, 'about.html')


def help_view(request):
    """
    Renders Help & FAQ page (/help/).
    """
    return render(request, 'help.html')


def settings_view(request):
    """
    Renders User Account Settings (/settings/).
    Handles updating name, email, artist profile info, and password change.
    """
    if not request.user.is_authenticated:
        return redirect('/?auth=login&next=/settings/')

    user = request.user
    artist_profile = getattr(user, 'artist_profile', None)
    success_msg = None
    error_msg = None

    if request.method == 'POST':
        action = request.POST.get('action', 'profile')

        if action == 'profile':
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            email = request.POST.get('email', '').strip()

            if email:
                user.email = email
            user.first_name = first_name
            user.last_name = last_name
            user.save()

            if user.is_creator and artist_profile:
                display_name = request.POST.get('display_name', '').strip()
                if display_name:
                    artist_profile.display_name = display_name
                artist_profile.bio = request.POST.get('bio', '').strip()
                artist_profile.is_accepting_commissions = ('is_accepting_commissions' in request.POST)

                if 'avatar' in request.FILES:
                    artist_profile.avatar = request.FILES['avatar']
                if 'cover_image' in request.FILES:
                    artist_profile.cover_image = request.FILES['cover_image']

                artist_profile.save()

            success_msg = 'Cập nhật thông tin cá nhân thành công.'

        elif action == 'password':
            old_password = request.POST.get('old_password', '')
            new_password = request.POST.get('new_password', '')
            confirm_password = request.POST.get('confirm_password', '')

            if not user.check_password(old_password):
                error_msg = 'Mật khẩu hiện tại không chính xác.'
            elif len(new_password) < 6:
                error_msg = 'Mật khẩu mới phải có tối thiểu 6 ký tự.'
            elif new_password != confirm_password:
                error_msg = 'Xác nhận mật khẩu mới không trùng khớp.'
            else:
                user.set_password(new_password)
                user.save()
                update_session_auth_hash(request, user)
                success_msg = 'Đổi mật khẩu thành công.'

    return render(request, 'settings.html', {
        'user': user,
        'artist_profile': artist_profile,
        'success_msg': success_msg,
        'error_msg': error_msg,
    })


def terms_view(request):
    """
    Renders Terms of Service draft (/terms/).
    """
    return render(request, 'terms.html')


def privacy_view(request):
    """
    Renders Privacy Policy draft (/privacy/).
    """
    return render(request, 'privacy.html')


def custom_404_view(request, exception=None):
    """
    Boutique styled 404 Not Found error page.
    """
    return render(request, '404.html', status=404)


def custom_403_view(request, exception=None):
    """
    Boutique styled 403 Forbidden error page.
    """
    return render(request, '403.html', status=403)


def api_root_overview(request):
    """
    Overview of the ARTFAIR Backend API.
    """
    return JsonResponse({
        'project': 'ARTFAIR Backend API',
        'version': '1.0.0',
        'description': 'Nền tảng giao dịch quyền sử dụng tác phẩm nghệ thuật và Commission.',
        'endpoints': {
            'home': '/',
            'artwork_detail_page': '/artworks/<slug>/',
            'artists_list': '/artists/',
            'artist_profile': '/artists/<username>/',
            'collections_list': '/collections/',
            'collection_detail': '/collections/<slug>/',
            'about': '/about/',
            'help': '/help/',
            'settings': '/settings/',
            'terms': '/terms/',
            'privacy': '/privacy/',
            'admin': '/admin/',
            'accounts': {
                'csrf_token': '/api/accounts/auth/csrf/',
                'register': '/api/accounts/auth/register/',
                'login': '/api/accounts/auth/login/',
                'logout': '/api/accounts/auth/logout/',
                'user_me': '/api/accounts/me/',
                'creator_profile': '/api/accounts/artist-profile/',
                'public_artist_profile': '/api/accounts/artists/<username>/',
            },
            'artworks': {
                'categories': '/api/artworks/categories/',
                'tags': '/api/artworks/tags/',
                'public_catalog': '/api/artworks/',
                'public_detail': '/api/artworks/<id_or_slug>/',
                'secure_download': '/api/artworks/<id>/download-file/',
                'orders_create': '/api/artworks/orders/',
                'orders_my_list': '/api/artworks/orders/my-orders/',
                'orders_detail': '/api/artworks/orders/<order_code>/',
                'orders_simulate_payment': '/api/artworks/orders/<order_code>/simulate-payment/',
                'creator_my_artworks': '/api/artworks/my-artworks/',
                'creator_detail': '/api/artworks/my-artworks/<id>/',
                'creator_publish': '/api/artworks/my-artworks/<id>/publish/',
                'creator_archive': '/api/artworks/my-artworks/<id>/archive/',
                'creator_licenses': '/api/artworks/my-artworks/<id>/licenses/',
                'creator_upload_file': '/api/artworks/my-artworks/<id>/original-file/',
            },
            'commissions': {
                'list_and_create': '/api/commissions/',
                'detail': '/api/commissions/<id>/',
            }
        }
    })
