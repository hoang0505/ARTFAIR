"""
build_static.py - ARTFAIR Static Site Generator for GitHub Pages
----------------------------------------------------------------
Compiles Django templates and static assets into the `dist/` directory
ready for deployment to GitHub Pages (https://hoang0505.github.io/ARTFAIR/).

Single Source of Truth:
- Edit styles, templates, and scripts exclusively in `frontend/`.
- Run this script (`python build_static.py`) to compile into `dist/`.
- Never edit `dist/` manually.
"""

import os
import sys
import shutil
import re
import json
from decimal import Decimal
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR / 'artfair_backend'
FRONTEND_DIR = BASE_DIR / 'frontend'
DIST_DIR = BASE_DIR / 'dist'

# Ensure artfair_backend is in sys.path
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.conf import settings
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.core.paginator import Paginator
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser

from artworks.models import Category, Tag, Artwork, Order, LicenseOption
from commissions.models import Commission

User = get_user_model()

# Constants for static build
REPO_PREFIX = '/ARTFAIR'
BACKEND_HOST = 'https://hoang0505.pythonanywhere.com'

# In-memory settings override for GitHub Pages static generation
settings.STATIC_URL = f'{REPO_PREFIX}/static/'
settings.MEDIA_URL = f'{BACKEND_HOST}/media/'


def rewrite_html(html_content):
    """
    Post-processes rendered HTML to ensure all internal links and asset references
    work seamlessly on GitHub Pages under the `/ARTFAIR/` repository path, while
    pointing API and media requests to PythonAnywhere.
    """
    def replace_url(match):
        attr = match.group(1)       # 'href', 'src', 'action'
        quote = match.group(2)      # '"' or "'"
        url = match.group(3)

        # Skip anchor links, external protocols, inline scripts, data URIs
        if url.startswith(('http://', 'https://', '//', '#', 'mailto:', 'tel:', 'javascript:', 'data:')):
            return f'{attr}={quote}{url}{quote}'

        # Already prefixed with repository path
        if url.startswith(f'{REPO_PREFIX}/') or url == REPO_PREFIX:
            return f'{attr}={quote}{url}{quote}'

        # Backend API endpoints
        if url.startswith('/api/') or url == '/api':
            return f'{attr}={quote}{BACKEND_HOST}{url}{quote}'

        # Backend Media endpoints
        if url.startswith('/media/') or url == '/media':
            return f'{attr}={quote}{BACKEND_HOST}{url}{quote}'

        # Static assets
        if url.startswith('/static/'):
            return f'{attr}={quote}{REPO_PREFIX}{url}{quote}'

        # Root-relative navigation link
        if url.startswith('/'):
            return f'{attr}={quote}{REPO_PREFIX}{url}{quote}'

        return f'{attr}={quote}{url}{quote}'

    # Match href="...", src="...", action="..."
    pattern = re.compile(r'\b(href|src|action)=([\'"])(/[^\'"\s]*)\2', re.IGNORECASE)
    rewritten = pattern.sub(replace_url, html_content)
    return rewritten


def write_page(relative_path, html_content):
    """
    Writes rendered HTML content to `dist/<relative_path>`.
    Validates that no unparsed Django template tags remain.
    """
    target = DIST_DIR / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)

    # Validate template tag leakage
    unparsed_matches = re.findall(r'(\{%[^\%]*%\}|\{\{[^\}]*\}\})', html_content)
    # Filter out valid client-side template literals or SVG patterns if any
    suspicious_tags = [m for m in unparsed_matches if not m.startswith('{{') or not m.endswith('}}')]
    # In Django templates, leftover {% ... %} or {{ ... }} are template syntax
    # Check specifically for unparsed Django tags:
    django_tags = [m for m in unparsed_matches if any(k in m for k in ['load', 'block', 'if ', 'for ', 'url ', 'static '])]
    if django_tags:
        raise ValueError(f"Unparsed Django tags detected in {relative_path}: {django_tags[:3]}")

    processed_html = rewrite_html(html_content)
    with open(target, 'w', encoding='utf-8') as f:
        f.write(processed_html)
    print(f"  [PAGE] -> dist/{relative_path}")


def sync_live_backend_data():
    """
    Safely queries live backend API (https://hoang0505.pythonanywhere.com/api/)
    to import any newly registered artists and published artworks into local SQLite
    before static site generation, ensuring they are compiled directly as static pages.
    """
    import urllib.request
    from django.utils.text import slugify
    from accounts.models import ArtistProfile

    try:
        req = urllib.request.Request(
            f"{BACKEND_HOST}/api/accounts/artists/",
            headers={'User-Agent': 'ARTFAIR-Static-Builder/1.0'}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                artists = json.loads(resp.read().decode('utf-8'))
                artists_list = artists.get('results', artists) if isinstance(artists, dict) else artists
                for a in artists_list:
                    uname = a.get('username')
                    if uname:
                        user, created = User.objects.get_or_create(
                            username=uname,
                            defaults={
                                'role': User.Role.CREATOR,
                                'email': f"{uname}@artfair.vn",
                                'is_active': True
                            }
                        )
                        if user.role != User.Role.CREATOR:
                            user.role = User.Role.CREATOR
                            user.save()
                        profile, _ = ArtistProfile.objects.get_or_create(user=user)
                        if a.get('display_name'):
                            profile.display_name = a['display_name']
                        if a.get('bio'):
                            profile.bio = a['bio']
                        if a.get('is_accepting_commissions') is not None:
                            profile.is_accepting_commissions = a['is_accepting_commissions']
                        if a.get('avatar'):
                            av_url = a['avatar']
                            profile.avatar.name = av_url.split('/media/', 1)[1] if '/media/' in av_url else av_url.lstrip('/')
                        if a.get('cover_image'):
                            cv_url = a['cover_image']
                            profile.cover_image.name = cv_url.split('/media/', 1)[1] if '/media/' in cv_url else cv_url.lstrip('/')
                        profile.save()
        print("  [SYNC] Live artists synced from backend.")
    except Exception as e:
        print(f"  [SYNC] Note: Live artists sync skipped ({e}). Using local database.")

    try:
        req = urllib.request.Request(
            f"{BACKEND_HOST}/api/artworks/",
            headers={'User-Agent': 'ARTFAIR-Static-Builder/1.0'}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                art_resp = json.loads(resp.read().decode('utf-8'))
                art_list = art_resp.get('results', art_resp) if isinstance(art_resp, dict) else art_resp
                for item in art_list:
                    slug = item.get('slug')
                    if not slug:
                        continue
                    creator_data = item.get('creator') or {}
                    uname = creator_data.get('username')
                    if not uname:
                        continue
                    creator, _ = User.objects.get_or_create(
                        username=uname,
                        defaults={'role': User.Role.CREATOR, 'email': f"{uname}@artfair.vn", 'is_active': True}
                    )
                    cat_data = item.get('category') or {}
                    cat_name = cat_data.get('name', 'Nghệ thuật số')
                    cat_slug = cat_data.get('slug') or slugify(cat_name)
                    cat, _ = Category.objects.get_or_create(
                        slug=cat_slug,
                        defaults={'name': cat_name}
                    )
                    artwork = Artwork.objects.filter(slug=slug).first()
                    if not artwork:
                        artwork = Artwork.objects.create(
                            creator=creator,
                            title=item.get('title', slug),
                            slug=slug,
                            description=item.get('description', ''),
                            category=cat,
                            style=item.get('style', ''),
                            status=Artwork.Status.PUBLISHED,
                        )
                    else:
                        artwork.creator = creator
                        artwork.category = cat
                        if item.get('title'): artwork.title = item['title']
                        if item.get('description'): artwork.description = item['description']
                        if item.get('style'): artwork.style = item['style']
                        artwork.status = Artwork.Status.PUBLISHED

                    if item.get('preview_image'):
                        p_url = str(item['preview_image'])
                        artwork.preview_image.name = p_url.split('/media/', 1)[1] if '/media/' in p_url else p_url.lstrip('/')
                    if item.get('watermarked_image'):
                        w_url = str(item['watermarked_image'])
                        artwork.watermarked_image.name = w_url.split('/media/', 1)[1] if '/media/' in w_url else w_url.lstrip('/')
                    artwork.save()

                    # License options
                    live_licenses = item.get('license_options') or []
                    for lo in live_licenses:
                        ltype = lo.get('license_type')
                        lprice = lo.get('price', 0)
                        lterms = lo.get('terms', '')
                        if ltype:
                            LicenseOption.objects.update_or_create(
                                artwork=artwork,
                                license_type=ltype,
                                defaults={'price': lprice, 'terms': lterms, 'is_active': True}
                            )
        print("  [SYNC] Live published artworks synced from backend.")
    except Exception as e:
        print(f"  [SYNC] Note: Live artworks sync skipped ({e}). Using local database.")


def build():
    print("=" * 60)
    print("ARTFAIR - Building Static Site for GitHub Pages")
    print(f"Base Repository Prefix: {REPO_PREFIX}")
    print(f"Live Backend API:       {BACKEND_HOST}")
    print("=" * 60)

    # 0. Sync live artists and artworks from PythonAnywhere backend
    sync_live_backend_data()

    # 1. Clean and initialize dist directory
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    # 2. Copy static assets from frontend/static/ to dist/static/
    src_static = FRONTEND_DIR / 'static'
    dst_static = DIST_DIR / 'static'
    if src_static.exists():
        shutil.copytree(src_static, dst_static)
        print(f"  [STATIC] Copied assets from {src_static} -> {dst_static}")

    # 3. Create .nojekyll for GitHub Pages
    (DIST_DIR / '.nojekyll').touch()
    print("  [SYSTEM] Created dist/.nojekyll")

    # Setup RequestFactory for rendering
    rf = RequestFactory()
    dummy_request = rf.get('/')
    dummy_request.user = AnonymousUser()

    # =========================================================================
    # 4. Render Core Pages
    # =========================================================================
    categories = list(Category.objects.all().order_by('name'))
    tags = list(Tag.objects.all().order_by('name'))
    creators = list(User.objects.filter(role=User.Role.CREATOR, is_active=True).exclude(username='admin').select_related('artist_profile').order_by('username'))
    gallery_artworks = list(Artwork.objects.filter(
        status=Artwork.Status.PUBLISHED
    ).select_related('creator', 'creator__artist_profile', 'category').prefetch_related('license_options').order_by('-created_at')[:8])
    featured_artworks = gallery_artworks[:3]

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

    # 4.1 Home Page
    home_html = render_to_string('home.html', {
        'categories': categories,
        'tags': tags,
        'styles': styles,
        'creators': creators,
        'featured_artworks': featured_artworks,
        'gallery_artworks': gallery_artworks,
    }, request=dummy_request)
    write_page('index.html', home_html)

    # 4.2 Artist Directory (/artists/)
    artists_data = []
    for artist in creators:
        artworks = Artwork.objects.filter(creator=artist, status=Artwork.Status.PUBLISHED).order_by('-created_at')
        artists_data.append({
            'artist': artist,
            'profile': getattr(artist, 'artist_profile', None),
            'artworks_count': artworks.count(),
            'sample_art': artworks.first(),
        })
    paginator = Paginator(artists_data, 12)
    page_obj = paginator.get_page(1)
    artists_html = render_to_string('artist_list.html', {
        'page_obj': page_obj,
        'q': '',
        'accepting': '',
        'total_artists': len(artists_data),
    }, request=dummy_request)
    write_page('artists/index.html', artists_html)

    # 4.3 Collections Index (/collections/)
    collections = []
    for cat in categories:
        published_artworks = Artwork.objects.filter(category=cat, status=Artwork.Status.PUBLISHED).order_by('-created_at')
        collections.append({
            'category': cat,
            'name': cat.name,
            'slug': cat.slug,
            'description': cat.description or f'Tuyển tập các tác phẩm nghệ thuật thuộc nhóm {cat.name} trên ARTFAIR.',
            'count': published_artworks.count(),
            'cover_art': published_artworks.first(),
        })
    collections_html = render_to_string('collections_list.html', {
        'collections': collections,
    }, request=dummy_request)
    write_page('collections/index.html', collections_html)

    # 4.4 Collection Detail Pages (/collections/<slug>/)
    for cat in categories:
        artworks_qs = Artwork.objects.filter(
            category=cat,
            status=Artwork.Status.PUBLISHED
        ).select_related('creator', 'creator__artist_profile').prefetch_related('license_options').order_by('-created_at')
        cat_paginator = Paginator(artworks_qs, 12)
        cat_page_obj = cat_paginator.get_page(1)
        cat_html = render_to_string('collection_detail.html', {
            'category': cat,
            'page_obj': cat_page_obj,
            'sort': '-created_at',
            'total_count': artworks_qs.count(),
        }, request=dummy_request)
        write_page(f'collections/{cat.slug}/index.html', cat_html)

    # 4.5 Published Artwork Detail Pages (/artworks/<slug>/)
    all_published_artworks = Artwork.objects.filter(
        status=Artwork.Status.PUBLISHED
    ).select_related('creator', 'creator__artist_profile', 'category', 'original_file').prefetch_related('tags', 'license_options')

    for art in all_published_artworks:
        license_options = art.license_options.filter(is_active=True).order_by('license_type')
        licenses_data = [
            {
                'id': lic.id,
                'type': lic.license_type,
                'name': lic.get_license_type_display(),
                'price': int(lic.price),
                'terms': lic.terms,
                'is_owned': False,
            }
            for lic in license_options
        ]
        other_artworks = Artwork.objects.filter(
            creator=art.creator,
            status=Artwork.Status.PUBLISHED
        ).exclude(id=art.id).select_related('category').prefetch_related('license_options').order_by('-created_at')[:4]

        art_html = render_to_string('artwork_detail.html', {
            'artwork': art,
            'license_options': license_options,
            'licenses_json': json.dumps(licenses_data),
            'owned_license_types': [],
            'is_owner': False,
            'is_favorited': False,
            'has_any_download_access': False,
            'original_file': getattr(art, 'original_file', None),
            'other_artworks': other_artworks,
        }, request=dummy_request)
        write_page(f'artworks/{art.slug}/index.html', art_html)

    # 4.6 User & Artist Public Profiles (/artists/<username>/)
    from accounts.models import ArtistReview
    all_users = User.objects.all().select_related('artist_profile').order_by('-id')
    seen_usernames = set()
    for user_obj in all_users:
        uname_lower = user_obj.username.lower()
        if uname_lower in seen_usernames:
            continue
        seen_usernames.add(uname_lower)
        if user_obj.is_creator:
            artworks_qs = Artwork.objects.filter(
                creator=user_obj,
                status=Artwork.Status.PUBLISHED
            ).select_related('category').prefetch_related('license_options').order_by('-created_at')
            artist_paginator = Paginator(artworks_qs, 8)
            artist_page_obj = artist_paginator.get_page(1)
            reviews = ArtistReview.objects.filter(artist=user_obj).select_related('reviewer').order_by('-created_at')
            total_art_count = artworks_qs.count()
            comm_count = Commission.objects.filter(creator=user_obj, status=Commission.Status.COMPLETED).count()
        else:
            artworks_qs = Artwork.objects.none()
            artist_paginator = Paginator(artworks_qs, 8)
            artist_page_obj = artist_paginator.get_page(1)
            reviews = ArtistReview.objects.none()
            total_art_count = 0
            comm_count = 0

        artist_html = render_to_string('artist_profile.html', {
            'artist': user_obj,
            'profile': getattr(user_obj, 'artist_profile', None),
            'page_obj': artist_page_obj,
            'total_artworks_count': total_art_count,
            'completed_commissions_count': comm_count,
            'is_owner': False,
            'reviews': reviews,
            'can_review': False,
            'eligible_order': None,
            'eligible_commission': None,
            'existing_user_review': None,
        }, request=dummy_request)
        write_page(f'artists/{user_obj.username}/index.html', artist_html)

    # 4.7 Commission Detail Pages (/commissions/<id>/)
    from commissions.serializers import CommissionDetailSerializer
    all_commissions = Commission.objects.all().select_related('buyer', 'creator', 'creator__artist_profile').prefetch_related('proposals', 'events')
    for comm in all_commissions:
        serializer = CommissionDetailSerializer(comm, context={'request': dummy_request})
        comm_html = render_to_string('commission_detail.html', {
            'commission': comm,
            'commission_json': json.dumps(serializer.data, default=str),
            'is_buyer': False,
            'is_creator': False,
            'user_role': 'GUEST',
        }, request=dummy_request)
        write_page(f'commissions/{comm.id}/index.html', comm_html)

    # 4.8 Information & Legal Pages
    about_html = render_to_string('about.html', {}, request=dummy_request)
    write_page('about/index.html', about_html)

    help_html = render_to_string('help.html', {}, request=dummy_request)
    write_page('help/index.html', help_html)

    terms_html = render_to_string('terms.html', {}, request=dummy_request)
    write_page('terms/index.html', terms_html)

    privacy_html = render_to_string('privacy.html', {}, request=dummy_request)
    write_page('privacy/index.html', privacy_html)

    # 4.9 User Portal Pages (Studio, Dashboard, Settings)
    # Neutral rendering with ZERO hardcoded private data.
    # Authenticated user data is dynamically and securely hydrated via live API.
    studio_html = render_to_string('studio.html', {
        'artworks': Artwork.objects.none(),
        'categories': categories,
        'tags': tags,
        'total_artworks': 0,
        'published_count': 0,
        'draft_count': 0,
        'archived_count': 0,
        'total_completed_orders': 0,
        'total_revenue': Decimal('0'),
        'artist_profile': None,
        'user': None,
    }, request=dummy_request)
    write_page('studio/index.html', studio_html)

    dash_html = render_to_string('dashboard.html', {
        'user': None,
        'artist_profile': None,
        'library_orders': Order.objects.none(),
        'my_orders': Order.objects.none(),
        'buyer_commissions': Commission.objects.none(),
        'user_favorites': [],
        'user_notifications': [],
        'creator_commissions': Commission.objects.none(),
        'financials': {'available_balance': 0, 'total_revenue': 0, 'total_withdrawn': 0},
    }, request=dummy_request)
    write_page('dashboard/index.html', dash_html)

    settings_html = render_to_string('settings.html', {
        'user': None,
        'artist_profile': None,
        'success_msg': None,
        'error_msg': None,
    }, request=dummy_request)
    write_page('settings/index.html', settings_html)


    # 4.10 404 Error Page with auto-redirection fallback for missing prefix
    raw_404_html = render_to_string('404.html', {}, request=dummy_request)
    # Insert smart prefix correction script into 404 page
    redirect_script = """
  <script>
    (function() {
      var p = window.location.pathname;
      if (!p.startsWith('/ARTFAIR/') && p !== '/ARTFAIR') {
        var cleanPath = p.replace(/^\\/+/, '');
        window.location.replace('/ARTFAIR/' + cleanPath + window.location.search + window.location.hash);
      }
    })();
  </script>
"""
    if '<head>' in raw_404_html:
        raw_404_html = raw_404_html.replace('<head>', '<head>' + redirect_script, 1)
    write_page('404.html', raw_404_html)

    print("=" * 60)
    print("Static build completed successfully in `dist/`!")
    print("=" * 60)


if __name__ == '__main__':
    build()
