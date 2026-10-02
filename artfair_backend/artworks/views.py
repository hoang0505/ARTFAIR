import os
from decimal import Decimal
from django.shortcuts import get_object_or_404
from django.http import FileResponse, Http404, HttpResponse
from django.db import transaction
from django.utils import timezone
from rest_framework import status, permissions, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from accounts.permissions import IsCreator, IsOwnerOrReadOnly
from .models import Category, Tag, Artwork, ArtworkFile, LicenseOption, Order, Withdrawal, get_creator_financials
from .filters import ArtworkFilter
from .serializers import (
    CategorySerializer,
    TagSerializer,
    LicenseOptionSerializer,
    ArtworkFileMetadataSerializer,
    PublicArtworkListSerializer,
    PublicArtworkDetailSerializer,
    CreatorArtworkSerializer,
    UploadArtworkFileSerializer,
    OrderSerializer,
    CreateOrderSerializer,
    PurchasedArtworkLibrarySerializer,
    WithdrawalSerializer,
    CreateWithdrawalSerializer,
)
from django.core.exceptions import ValidationError
from .utils import (
    extract_metadata_and_inspect,
    generate_watermarked_preview,
    validate_file_size,
    validate_file_extension,
    ALLOWED_ORIGINAL_EXTENSIONS,
    ALLOWED_PREVIEW_EXTENSIONS,
    generate_license_certificate_pdf,
)


class CategoryListView(generics.ListAPIView):
    """
    Public list of all art categories.
    """
    permission_classes = [permissions.AllowAny]
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    pagination_class = None


class TagListView(generics.ListAPIView):
    """
    Public list of all tags.
    """
    permission_classes = [permissions.AllowAny]
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    pagination_class = None


class PublicArtworkListView(generics.ListAPIView):
    """
    Public catalog of PUBLISHED artworks.
    Supports filtering by category, artist, tag, license_type, min_price, max_price.
    Supports search by title, description, and tags.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = PublicArtworkListSerializer
    filterset_class = ArtworkFilter
    search_fields = ['title', 'description', 'tags__name', 'category__name']
    ordering_fields = ['created_at', 'title']
    ordering = ['-created_at']

    def get_queryset(self):
        return Artwork.objects.filter(
            status=Artwork.Status.PUBLISHED
        ).select_related('creator', 'creator__artist_profile', 'category').prefetch_related('tags', 'license_options')


class PublicArtworkDetailView(generics.RetrieveAPIView):
    """
    Public detail view of a single PUBLISHED artwork.
    Lookup by ID or slug.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = PublicArtworkDetailSerializer

    def get_object(self):
        lookup = self.kwargs.get('lookup')
        queryset = Artwork.objects.filter(
            status=Artwork.Status.PUBLISHED
        ).select_related('creator', 'creator__artist_profile', 'category').prefetch_related('tags', 'license_options')

        if lookup.isdigit():
            obj = queryset.filter(id=int(lookup)).first()
        else:
            obj = queryset.filter(slug=lookup).first()

        if not obj:
            raise Http404("Tác phẩm không tồn tại hoặc chưa được phát hành.")
        return obj


class CreatorArtworkListCreateView(generics.ListCreateAPIView):
    """
    Creator dashboard area:
    - GET: View all artworks owned by current creator (DRAFT, PUBLISHED, ARCHIVED).
    - POST: Create a new artwork draft. Creator is automatically bound to request.user.
    """
    permission_classes = [permissions.IsAuthenticated, IsCreator]
    serializer_class = CreatorArtworkSerializer

    def get_queryset(self):
        qs = Artwork.objects.filter(
            creator=self.request.user
        ).select_related('category').prefetch_related('tags', 'license_options')

        status_param = self.request.query_params.get('status')
        if status_param in Artwork.Status.values:
            qs = qs.filter(status=status_param)
        return qs

    def perform_create(self, serializer):
        serializer.save(creator=self.request.user)


class CreatorArtworkDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Creator inspects, updates, or deletes their own artwork.
    """
    permission_classes = [permissions.IsAuthenticated, IsCreator, IsOwnerOrReadOnly]
    serializer_class = CreatorArtworkSerializer

    def get_queryset(self):
        return Artwork.objects.filter(
            creator=self.request.user
        ).select_related('category').prefetch_related('tags', 'license_options')


class ArtworkPublishView(APIView):
    """
    Endpoint to publish an artwork:
    Enforces that:
    1. Artwork has preview image.
    2. Artwork has original deliverable file.
    3. Artwork has both PERSONAL and COMMERCIAL active license tiers with price > 0.
    """
    permission_classes = [permissions.IsAuthenticated, IsCreator]

    def post(self, request, pk):
        artwork = get_object_or_404(Artwork, pk=pk, creator=request.user)
        can_publish, blocking_reasons = artwork.can_be_published()

        if not can_publish:
            return Response({
                'detail': 'Tác phẩm chưa đủ điều kiện để phát hành.',
                'blocking_reasons': blocking_reasons
            }, status=status.HTTP_400_BAD_REQUEST)

        artwork.status = Artwork.Status.PUBLISHED
        artwork.save(update_fields=['status', 'updated_at'])

        return Response({
            'detail': 'Tác phẩm đã được phát hành thành công lên sàn ARTFAIR.',
            'artwork': CreatorArtworkSerializer(artwork, context={'request': request}).data
        }, status=status.HTTP_200_OK)


class ArtworkArchiveView(APIView):
    """
    Endpoint to archive a creator's artwork.
    """
    permission_classes = [permissions.IsAuthenticated, IsCreator]

    def post(self, request, pk):
        artwork = get_object_or_404(Artwork, pk=pk, creator=request.user)
        artwork.status = Artwork.Status.ARCHIVED
        artwork.save(update_fields=['status', 'updated_at'])

        return Response({
            'detail': 'Tác phẩm đã được chuyển sang trạng thái lưu trữ.',
            'status': artwork.status
        }, status=status.HTTP_200_OK)


class CreatorArtworkLicenseView(APIView):
    """
    Manage license options (PERSONAL / COMMERCIAL) for a specific artwork.
    """
    permission_classes = [permissions.IsAuthenticated, IsCreator]

    def get(self, request, artwork_id):
        artwork = get_object_or_404(Artwork, pk=artwork_id, creator=request.user)
        options = artwork.license_options.all()
        return Response(LicenseOptionSerializer(options, many=True).data)

    def post(self, request, artwork_id):
        artwork = get_object_or_404(Artwork, pk=artwork_id, creator=request.user)
        license_type = request.data.get('license_type')
        price = request.data.get('price')
        terms = request.data.get('terms', '')
        is_active = request.data.get('is_active', True)

        if license_type not in LicenseOption.LicenseType.values:
            return Response(
                {'detail': f"Loại quyền không hợp lệ. Phải là một trong: {list(LicenseOption.LicenseType.values)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            price_dec = Decimal(str(price))
            if price_dec <= Decimal('0'):
                return Response({'price': 'Giá bán phải lớn hơn 0 VND.'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response({'price': 'Giá bán không hợp lệ.'}, status=status.HTTP_400_BAD_REQUEST)

        # Update or create the license option
        option, created = LicenseOption.objects.update_or_create(
            artwork=artwork,
            license_type=license_type,
            defaults={
                'price': price_dec,
                'terms': terms,
                'is_active': is_active
            }
        )

        return Response(
            LicenseOptionSerializer(option).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


class CreatorArtworkFileUploadView(APIView):
    """
    Upload original delivery file for creator's artwork.
    - Inspects metadata (format, dimensions, DPI, color mode).
    - If raster image: generates watermarked preview automatically using Pillow.
    - If vector or PSD/AI: requires preview_image if not already present.
    - Securely stores original file in protected storage.
    """
    permission_classes = [permissions.IsAuthenticated, IsCreator]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, artwork_id):
        artwork = get_object_or_404(Artwork, pk=artwork_id, creator=request.user)
        serializer = UploadArtworkFileSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        uploaded_file = serializer.validated_data['file']
        custom_preview = serializer.validated_data.get('preview_image')

        # 1. Inspect uploaded file metadata
        metadata = extract_metadata_and_inspect(uploaded_file)

        # 2. Check preview availability
        if not metadata['can_generate_preview'] and not custom_preview and not artwork.preview_image:
            return Response({
                'detail': (
                    f"Tệp gốc ở định dạng '{metadata['format']}' không thể tự động tạo preview. "
                    "Vui lòng tải kèm ảnh xem trước (JPG/PNG) trong trường 'preview_image'."
                )
            }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            # 3. Handle preview generation / saving
            if custom_preview:
                # User provided custom preview image: generate watermarked version from it
                preview_file = generate_watermarked_preview(custom_preview)
                artwork.preview_image.save(preview_file.name, preview_file, save=True)
            elif metadata['can_generate_preview']:
                # Generate watermarked preview from the uploaded raster original
                preview_file = generate_watermarked_preview(uploaded_file)
                artwork.preview_image.save(preview_file.name, preview_file, save=True)

            # 4. Save or replace ArtworkFile
            artwork_file, _ = ArtworkFile.objects.update_or_create(
                artwork=artwork,
                defaults={
                    'file': uploaded_file,
                    'original_filename': uploaded_file.name,
                    'file_format': metadata['format'],
                    'file_size_bytes': metadata['size'],
                    'width': metadata['width'],
                    'height': metadata['height'],
                    'dpi': metadata['dpi'],
                    'color_mode': metadata['color_mode'],
                }
            )

        return Response({
            'detail': 'Tải lên tệp gốc thành công.',
            'file_metadata': ArtworkFileMetadataSerializer(artwork_file, context={'request': request}).data,
            'artwork': CreatorArtworkSerializer(artwork, context={'request': request}).data
        }, status=status.HTTP_200_OK)


class CreatorStudioWizardPublishView(APIView):
    """
    Unified 3-Step Wizard for Creator Studio to create and publish artwork:
    - Step 1: Upload master file (validates format, size, auto-generates watermarked preview or requires custom preview for vector/archive)
    - Step 2: Details (title, description, category_id, tag_ids)
    - Step 3: Licenses & Confirmation (personal_price, commercial_price, terms, rights confirmation)
    - Action: 'publish' (strict eligibility check) or 'draft'
    """
    permission_classes = [permissions.IsAuthenticated, IsCreator]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        action = request.data.get('action', 'publish').lower()
        title = request.data.get('title', '').strip()
        description = request.data.get('description', '').strip()
        category_id = request.data.get('category_id')
        tag_ids_raw = request.data.getlist('tag_ids') if hasattr(request.data, 'getlist') else request.data.get('tag_ids', [])

        uploaded_file = request.FILES.get('file')
        custom_preview = request.FILES.get('preview_image')

        personal_price = request.data.get('personal_price')
        personal_terms = request.data.get('personal_terms', '').strip()
        commercial_price = request.data.get('commercial_price')
        commercial_terms = request.data.get('commercial_terms', '').strip()
        rights_confirmed = str(request.data.get('rights_confirmed', '')).lower() in ('true', '1', 'on', 'yes')

        errors = {}

        if not title:
            errors['title'] = ['Tiêu đề tác phẩm không được để trống.']

        category = None
        if not category_id:
            errors['category_id'] = ['Vui lòng chọn danh mục cho tác phẩm.']
        else:
            try:
                category = Category.objects.get(pk=category_id)
            except (Category.DoesNotExist, ValueError):
                errors['category_id'] = ['Danh mục được chọn không hợp lệ.']

        if not uploaded_file:
            if action == 'publish':
                errors['file'] = ['Vui lòng chọn tệp gốc bàn giao cho tác phẩm.']
        else:
            try:
                validate_file_size(uploaded_file, label="tệp bàn giao gốc")
                validate_file_extension(uploaded_file.name, ALLOWED_ORIGINAL_EXTENSIONS)
            except ValidationError as ve:
                errors['file'] = [str(ve)]

        if custom_preview:
            try:
                validate_file_size(custom_preview, max_mb=10, label="ảnh xem trước")
                validate_file_extension(custom_preview.name, ALLOWED_PREVIEW_EXTENSIONS)
            except ValidationError as ve:
                errors['preview_image'] = [str(ve)]

        metadata = None
        if uploaded_file and 'file' not in errors:
            metadata = extract_metadata_and_inspect(uploaded_file)
            if not metadata['can_generate_preview'] and not custom_preview:
                errors['preview_image'] = [
                    f"Tệp gốc ở định dạng '{metadata['format']}' không thể tự động tạo preview. "
                    "Vui lòng chọn thêm tệp ảnh xem trước (JPG/PNG)."
                ]

        personal_price_dec = None
        if personal_price:
            try:
                personal_price_dec = Decimal(str(personal_price))
                if personal_price_dec <= Decimal('0'):
                    errors['personal_price'] = ['Giá gói Cá nhân phải lớn hơn 0 VND.']
            except Exception:
                errors['personal_price'] = ['Giá gói Cá nhân không hợp lệ.']
        elif action == 'publish':
            errors['personal_price'] = ['Vui lòng nhập giá gói Cá nhân (lớn hơn 0 VND).']

        commercial_price_dec = None
        if commercial_price:
            try:
                commercial_price_dec = Decimal(str(commercial_price))
                if commercial_price_dec <= Decimal('0'):
                    errors['commercial_price'] = ['Giá gói Thương mại phải lớn hơn 0 VND.']
            except Exception:
                errors['commercial_price'] = ['Giá gói Thương mại không hợp lệ.']
        elif action == 'publish':
            errors['commercial_price'] = ['Vui lòng nhập giá gói Thương mại (lớn hơn 0 VND).']

        if action == 'publish' and not rights_confirmed:
            errors['rights_confirmed'] = ['Bạn phải tích cam kết quyền tác giả và quyền đăng bán hợp pháp.']

        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            artwork = Artwork.objects.create(
                creator=request.user,
                title=title or 'Bản nháp tác phẩm mới',
                description=description,
                category=category or Category.objects.first(),
                status=Artwork.Status.DRAFT
            )

            # Assign tags
            if tag_ids_raw:
                clean_tags = []
                if isinstance(tag_ids_raw, str):
                    clean_tags = [int(t.strip()) for t in tag_ids_raw.split(',') if t.strip().isdigit()]
                elif isinstance(tag_ids_raw, list):
                    for t in tag_ids_raw:
                        if isinstance(t, str) and ',' in t:
                            clean_tags.extend([int(x.strip()) for x in t.split(',') if x.strip().isdigit()])
                        elif str(t).isdigit():
                            clean_tags.append(int(t))
                artwork.tags.set(clean_tags)

            # Preview & ArtworkFile
            if custom_preview:
                preview_file = generate_watermarked_preview(custom_preview)
                artwork.preview_image.save(preview_file.name, preview_file, save=True)
            elif metadata and metadata['can_generate_preview'] and uploaded_file:
                preview_file = generate_watermarked_preview(uploaded_file)
                artwork.preview_image.save(preview_file.name, preview_file, save=True)

            if uploaded_file:
                ArtworkFile.objects.create(
                    artwork=artwork,
                    file=uploaded_file,
                    original_filename=uploaded_file.name,
                    file_format=metadata['format'] if metadata else 'UNKNOWN',
                    file_size_bytes=metadata['size'] if metadata else uploaded_file.size,
                    width=metadata['width'] if metadata else None,
                    height=metadata['height'] if metadata else None,
                    dpi=metadata['dpi'] if metadata else None,
                    color_mode=metadata['color_mode'] if metadata else '',
                )

            # Licenses
            if personal_price_dec and personal_price_dec > Decimal('0'):
                LicenseOption.objects.create(
                    artwork=artwork,
                    license_type=LicenseOption.LicenseType.PERSONAL,
                    price=personal_price_dec,
                    terms=personal_terms or 'Quyền sử dụng phi thương mại, không độc quyền.'
                )

            if commercial_price_dec and commercial_price_dec > Decimal('0'):
                LicenseOption.objects.create(
                    artwork=artwork,
                    license_type=LicenseOption.LicenseType.COMMERCIAL,
                    price=commercial_price_dec,
                    terms=commercial_terms or 'Quyền sử dụng thương mại, không độc quyền.'
                )

            # If publish requested, strictly verify all publishing criteria
            if action == 'publish':
                can_publish, blocking_reasons = artwork.can_be_published()
                if not can_publish:
                    return Response({
                        'detail': 'Tác phẩm chưa đủ điều kiện để phát hành.',
                        'blocking_reasons': blocking_reasons
                    }, status=status.HTTP_400_BAD_REQUEST)
                artwork.status = Artwork.Status.PUBLISHED
                artwork.save(update_fields=['status', 'updated_at'])

        return Response({
            'detail': 'Phát hành tác phẩm thành công lên ARTFAIR!' if action == 'publish' else 'Đã lưu bản nháp tác phẩm thành công.',
            'artwork': CreatorArtworkSerializer(artwork, context={'request': request}).data
        }, status=status.HTTP_201_CREATED)


class CreatorStudioWizardEditView(APIView):
    """
    Edit existing artwork in Creator Studio:
    - Update title, description, category, tags
    - Update prices & terms for PERSONAL and COMMERCIAL
    - Replace file and/or preview if new files uploaded
    - Actions: 'publish' (if ready), 'archive' (if published), 'update' (save modifications)
    - Anti-tampering: Creator can ONLY edit their own artworks (403 if other creator's artwork).
    """
    permission_classes = [permissions.IsAuthenticated, IsCreator]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk):
        artwork = get_object_or_404(Artwork, pk=pk)
        if artwork.creator != request.user and not request.user.is_staff:
            return Response(
                {'detail': 'Bạn không có quyền chỉnh sửa tác phẩm của nghệ sĩ khác.'},
                status=status.HTTP_403_FORBIDDEN
            )

        title = request.data.get('title', '').strip()
        description = request.data.get('description', '').strip()
        category_id = request.data.get('category_id')
        tag_ids_raw = request.data.getlist('tag_ids') if hasattr(request.data, 'getlist') else request.data.get('tag_ids', [])
        action = request.data.get('action', 'update').lower()

        uploaded_file = request.FILES.get('file')
        custom_preview = request.FILES.get('preview_image')

        personal_price = request.data.get('personal_price')
        personal_terms = request.data.get('personal_terms', '').strip()
        commercial_price = request.data.get('commercial_price')
        commercial_terms = request.data.get('commercial_terms', '').strip()

        errors = {}

        if 'title' in request.data:
            if not title:
                errors['title'] = ['Tiêu đề không được để trống.']
            else:
                artwork.title = title

        if 'description' in request.data:
            artwork.description = description

        if category_id:
            try:
                category = Category.objects.get(pk=category_id)
                artwork.category = category
            except (Category.DoesNotExist, ValueError):
                errors['category_id'] = ['Danh mục không hợp lệ.']

        if uploaded_file:
            try:
                validate_file_size(uploaded_file, label="tệp bàn giao gốc")
                validate_file_extension(uploaded_file.name, ALLOWED_ORIGINAL_EXTENSIONS)
            except ValidationError as ve:
                errors['file'] = [str(ve)]

        if custom_preview:
            try:
                validate_file_size(custom_preview, max_mb=10, label="ảnh xem trước")
                validate_file_extension(custom_preview.name, ALLOWED_PREVIEW_EXTENSIONS)
            except ValidationError as ve:
                errors['preview_image'] = [str(ve)]

        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            artwork.save()

            if tag_ids_raw:
                clean_tags = []
                if isinstance(tag_ids_raw, str):
                    clean_tags = [int(t.strip()) for t in tag_ids_raw.split(',') if t.strip().isdigit()]
                elif isinstance(tag_ids_raw, list):
                    for t in tag_ids_raw:
                        if isinstance(t, str) and ',' in t:
                            clean_tags.extend([int(x.strip()) for x in t.split(',') if x.strip().isdigit()])
                        elif str(t).isdigit():
                            clean_tags.append(int(t))
                artwork.tags.set(clean_tags)

            # Handle file replacement if uploaded
            if uploaded_file:
                metadata = extract_metadata_and_inspect(uploaded_file)
                if custom_preview:
                    preview_file = generate_watermarked_preview(custom_preview)
                    artwork.preview_image.save(preview_file.name, preview_file, save=True)
                elif metadata['can_generate_preview']:
                    preview_file = generate_watermarked_preview(uploaded_file)
                    artwork.preview_image.save(preview_file.name, preview_file, save=True)

                ArtworkFile.objects.update_or_create(
                    artwork=artwork,
                    defaults={
                        'file': uploaded_file,
                        'original_filename': uploaded_file.name,
                        'file_format': metadata['format'],
                        'file_size_bytes': metadata['size'],
                        'width': metadata['width'],
                        'height': metadata['height'],
                        'dpi': metadata['dpi'],
                        'color_mode': metadata['color_mode'],
                    }
                )
            elif custom_preview:
                preview_file = generate_watermarked_preview(custom_preview)
                artwork.preview_image.save(preview_file.name, preview_file, save=True)

            # Update licenses if provided
            if personal_price:
                p_dec = Decimal(str(personal_price))
                if p_dec > Decimal('0'):
                    LicenseOption.objects.update_or_create(
                        artwork=artwork,
                        license_type=LicenseOption.LicenseType.PERSONAL,
                        defaults={
                            'price': p_dec,
                            'terms': personal_terms or 'Quyền sử dụng phi thương mại, không độc quyền.',
                            'is_active': True
                        }
                    )

            if commercial_price:
                c_dec = Decimal(str(commercial_price))
                if c_dec > Decimal('0'):
                    LicenseOption.objects.update_or_create(
                        artwork=artwork,
                        license_type=LicenseOption.LicenseType.COMMERCIAL,
                        defaults={
                            'price': c_dec,
                            'terms': commercial_terms or 'Quyền sử dụng thương mại, không độc quyền.',
                            'is_active': True
                        }
                    )

            # Actions: publish or archive
            if action == 'publish':
                can_publish, blocking_reasons = artwork.can_be_published()
                if not can_publish:
                    return Response({
                        'detail': 'Tác phẩm chưa đủ điều kiện để phát hành.',
                        'blocking_reasons': blocking_reasons
                    }, status=status.HTTP_400_BAD_REQUEST)
                artwork.status = Artwork.Status.PUBLISHED
                artwork.save(update_fields=['status', 'updated_at'])
            elif action == 'archive':
                artwork.status = Artwork.Status.ARCHIVED
                artwork.save(update_fields=['status', 'updated_at'])

        return Response({
            'detail': 'Cập nhật tác phẩm thành công!',
            'artwork': CreatorArtworkSerializer(artwork, context={'request': request}).data
        }, status=status.HTTP_200_OK)


class ArtworkFileDownloadView(APIView):
    """
    Secure endpoint to download the original delivery file.
    PERMISSION:
    - Artwork Creator owner
    - Staff / Superusers
    - Buyers who completed purchase (Order.Status.COMPLETED)
    Guests and unauthorized users are strictly denied (HTTP 403 / 401).
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, artwork_id):
        artwork = get_object_or_404(Artwork, pk=artwork_id)

        # Check if buyer has completed order
        has_purchased = Order.objects.filter(
            buyer=request.user,
            artwork=artwork,
            status=Order.Status.COMPLETED
        ).exists()

        # Check permission: artwork creator, staff, or buyer with completed order
        if artwork.creator != request.user and not request.user.is_staff and not has_purchased:
            return Response(
                {'detail': 'Bạn không có quyền tải tệp gốc của tác phẩm này.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if not hasattr(artwork, 'original_file') or not artwork.original_file.file:
            raise Http404("Tác phẩm chưa có tệp gốc bàn giao.")

        original_file = artwork.original_file
        file_path = original_file.file.path

        if not os.path.exists(file_path):
            raise Http404("Tệp không tồn tại trên hệ thống lưu trữ.")

        response = FileResponse(
            open(file_path, 'rb'),
            as_attachment=True,
            filename=original_file.original_filename
        )
        return response


class CreateOrderView(APIView):
    """
    Create a new pending order to purchase a license option for an artwork.
    Enforces that:
    - Buyer cannot buy their own artwork.
    - Price is 100% backend-enforced from database.
    - Cannot buy license already owned.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = CreateOrderSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        order = serializer.save()
        return Response(
            OrderSerializer(order, context={'request': request}).data,
            status=status.HTTP_201_CREATED
        )


class SimulatePaymentView(APIView):
    """
    Simulated mock payment gateway for an order.
    Supports actions: 'SUCCESS', 'FAILED', 'CANCEL'.
    Only the order owner (buyer) can perform this.
    Prevents duplicate payment if already COMPLETED.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, order_code):
        order = get_object_or_404(Order, order_code=order_code)

        if order.buyer != request.user and not request.user.is_staff:
            return Response(
                {'detail': 'Bạn không có quyền thao tác trên đơn hàng này.'},
                status=status.HTTP_403_FORBIDDEN
            )

        action = request.data.get('action', '').upper()
        if action not in ['SUCCESS', 'FAILED', 'CANCEL']:
            return Response(
                {'detail': "Hành động thanh toán không hợp lệ. Phải là 'SUCCESS', 'FAILED' hoặc 'CANCEL'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Idempotency / state check
        if order.status == Order.Status.COMPLETED:
            return Response({
                'detail': 'Đơn hàng đã được thanh toán thành công trước đó.',
                'order': OrderSerializer(order, context={'request': request}).data
            }, status=status.HTTP_200_OK)

        if action == 'SUCCESS':
            order.status = Order.Status.COMPLETED
            order.completed_at = timezone.now()
            order.save(update_fields=['status', 'completed_at'])

            try:
                from accounts.notifications import create_notification
                create_notification(
                    recipient=order.buyer,
                    title="Mua quyền tác phẩm thành công",
                    message=f"Đơn hàng #{order.order_code} đã thanh toán thành công. Bạn đã sở hữu gói quyền {order.get_license_type_display()} của tác phẩm '{order.artwork.title}'.",
                    notification_type='ORDER_COMPLETED',
                    target_url='/dashboard/#tab-orders',
                    reference_id=f"order_buyer_{order.order_code}"
                )
                create_notification(
                    recipient=order.artwork.creator,
                    title="Lượt mua tác phẩm mới!",
                    message=f"Người mua @{order.buyer.username} vừa mua gói quyền {order.get_license_type_display()} của tác phẩm '{order.artwork.title}'. Doanh thu: +{int(order.price_paid):,}₫.",
                    notification_type='CREATOR_SALE',
                    target_url='/dashboard/#tab-revenue',
                    reference_id=f"order_creator_{order.order_code}"
                )
            except Exception:
                pass

            return Response({
                'detail': f'Thanh toán mô phỏng thành công! Bạn đã sở hữu gói quyền {order.get_license_type_display()}.',
                'order': OrderSerializer(order, context={'request': request}).data
            }, status=status.HTTP_200_OK)

        elif action == 'FAILED':
            order.status = Order.Status.FAILED
            order.save(update_fields=['status'])
            return Response({
                'detail': 'Thanh toán mô phỏng thất bại. Quyền sử dụng tác phẩm chưa được cấp.',
                'order': OrderSerializer(order, context={'request': request}).data
            }, status=status.HTTP_200_OK)

        elif action == 'CANCEL':
            order.status = Order.Status.CANCELLED
            order.save(update_fields=['status'])
            return Response({
                'detail': 'Giao dịch thanh toán đã được hủy theo yêu cầu.',
                'order': OrderSerializer(order, context={'request': request}).data
            }, status=status.HTTP_200_OK)


class MyOrdersListView(generics.ListAPIView):
    """
    List all orders of current authenticated buyer.
    Prepared for Screen 04 usage.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OrderSerializer

    def get_queryset(self):
        return Order.objects.filter(
            buyer=self.request.user
        ).select_related(
            'artwork',
            'artwork__creator',
            'artwork__creator__artist_profile',
            'artwork__category'
        ).order_by('-created_at')


class OrderDetailView(generics.RetrieveAPIView):
    """
    Retrieve single order by order_code.
    Only order buyer or staff can access.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OrderSerializer
    lookup_field = 'order_code'

    def get_queryset(self):
        if self.request.user.is_staff:
            return Order.objects.all().select_related('artwork', 'artwork__creator', 'artwork__creator__artist_profile')
        return Order.objects.filter(
            buyer=self.request.user
        ).select_related('artwork', 'artwork__creator', 'artwork__creator__artist_profile')



class MyLibraryListView(generics.ListAPIView):
    """
    List of artworks purchased by current authenticated buyer (Screen 04).
    Only completed orders are included.
    Distinct per license option (PERSONAL vs COMMERCIAL).
    Users retain access even if artwork is archived/unpublished.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PurchasedArtworkLibrarySerializer

    def get_queryset(self):
        return Order.objects.filter(
            buyer=self.request.user,
            status=Order.Status.COMPLETED
        ).select_related(
            'artwork',
            'artwork__creator',
            'artwork__creator__artist_profile',
            'artwork__original_file'
        ).order_by('-completed_at')


class OrderCertificatePDFView(APIView):
    """
    Export PDF Certificate for an artwork license purchase (Screen 04).
    PERMISSION:
    - Only the order's buyer or staff/admin can download.
    - Only completed orders (Order.Status.COMPLETED) are eligible.
    Guarantees non-exclusive license and simulated payment notice.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, order_code):
        order = get_object_or_404(
            Order.objects.select_related('artwork', 'artwork__creator', 'artwork__creator__artist_profile', 'buyer'),
            order_code=order_code
        )

        if order.buyer != request.user and not request.user.is_staff:
            return Response(
                {'detail': 'Bạn không có quyền tải chứng nhận bản quyền của đơn hàng này.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if order.status != Order.Status.COMPLETED:
            return Response(
                {'detail': 'Chỉ đơn hàng đã hoàn tất thanh toán mới được cấp chứng nhận bản quyền.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        pdf_bytes = generate_license_certificate_pdf(order)

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        filename = f"Chung_Nhan_Ban_Quyen_{order.order_code}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class CreatorDashboardAPIView(APIView):
    """
    API for Creator Sales & Revenue Dashboard (Screen 04).
    Computes real sales revenue, withdrawals, available balance,
    and returns sales transactions and withdrawal records.
    """
    permission_classes = [permissions.IsAuthenticated, IsCreator]

    def get(self, request):
        user = request.user
        financials = get_creator_financials(user)

        user_artworks = Artwork.objects.filter(creator=user)
        total_artworks = user_artworks.count()
        published_artworks_count = user_artworks.filter(status=Artwork.Status.PUBLISHED).count()

        completed_sales = Order.objects.filter(
            artwork__creator=user,
            status=Order.Status.COMPLETED
        ).select_related('artwork', 'buyer').order_by('-completed_at')

        total_completed_sales_count = completed_sales.count()

        sales_transactions = [
            {
                'order_code': order.order_code,
                'artwork_title': order.artwork.title,
                'artwork_slug': order.artwork.slug,
                'buyer_username': order.buyer.username,
                'license_type': order.license_type,
                'license_name': order.get_license_type_display(),
                'price_paid': int(order.price_paid),
                'completed_at': order.completed_at.strftime('%d/%m/%Y %H:%M') if order.completed_at else '',
            }
            for order in completed_sales[:50]
        ]

        withdrawals = Withdrawal.objects.filter(creator=user).order_by('-created_at')
        withdrawals_data = WithdrawalSerializer(withdrawals, many=True).data

        weekly_sales = []
        if total_completed_sales_count > 0:
            from django.db.models.functions import TruncWeek
            from django.db.models import Sum, Count
            weekly_qs = Order.objects.filter(
                artwork__creator=user,
                status=Order.Status.COMPLETED,
                completed_at__isnull=False
            ).annotate(
                week=TruncWeek('completed_at')
            ).values('week').annotate(
                revenue=Sum('price_paid'),
                count=Count('id')
            ).order_by('week')

            for item in weekly_qs:
                if item['week']:
                    weekly_sales.append({
                        'label': item['week'].strftime('Tuần %W (%d/%m)'),
                        'revenue': int(item['revenue'] or 0),
                        'count': item['count'],
                    })

        return Response({
            'total_artworks': total_artworks,
            'published_artworks_count': published_artworks_count,
            'total_completed_sales_count': total_completed_sales_count,
            'total_revenue': int(financials['total_revenue']),
            'total_withdrawn': int(financials['total_withdrawn']),
            'available_balance': int(financials['available_balance']),
            'sales_transactions': sales_transactions,
            'withdrawals': withdrawals_data,
            'weekly_sales': weekly_sales,
        })


class CreatorWithdrawalCreateView(APIView):
    """
    Create a simulated revenue withdrawal request (Screen 04).
    Verifies amount > 0 and amount <= available_balance.
    Executes atomically to prevent race conditions or negative balances.
    """
    permission_classes = [permissions.IsAuthenticated, IsCreator]

    def post(self, request):
        serializer = CreateWithdrawalSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        amount = serializer.validated_data['amount']
        note = serializer.validated_data.get('note', 'Rút doanh thu bán quyền sử dụng tác phẩm (Mô phỏng)')

        with transaction.atomic():
            financials = get_creator_financials(request.user)
            available = financials['available_balance']

            if amount > available:
                return Response({
                    'detail': f'Số tiền yêu cầu rút ({int(amount):,} VND) vượt quá số dư khả dụng ({int(available):,} VND).',
                    'available_balance': int(available)
                }, status=status.HTTP_400_BAD_REQUEST)

            withdrawal = Withdrawal.objects.create(
                creator=request.user,
                amount=amount,
                status=Withdrawal.Status.COMPLETED,
                note=note
            )

            updated_financials = get_creator_financials(request.user)

            try:
                from accounts.notifications import create_notification
                create_notification(
                    recipient=request.user,
                    title="Giải ngân doanh thu thành công (Mô phỏng)",
                    message=f"Yêu cầu rút tiền #{withdrawal.withdrawal_code} với số tiền {int(amount):,}₫ đã được giải ngân thành công vào số dư của bạn.",
                    notification_type='WITHDRAWAL_STATUS',
                    target_url='/dashboard/#tab-revenue',
                    reference_id=f"wd_{withdrawal.id}"
                )
            except Exception:
                pass

        return Response({
            'detail': f'Yêu cầu rút {int(amount):,} VND mô phỏng thành công! Đã ghi nhận giải ngân vào số dư của bạn.',
            'withdrawal': WithdrawalSerializer(withdrawal).data,
            'new_available_balance': int(updated_financials['available_balance']),
            'total_withdrawn': int(updated_financials['total_withdrawn'])
        }, status=status.HTTP_201_CREATED)


class ArtworkFavoriteToggleView(APIView):
    """
    Toggle favorite / wishlist status for an artwork.
    Requires authentication (Guests are intercepted by frontend modal).
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        from .models import ArtworkFavorite
        artwork = get_object_or_404(Artwork, pk=pk, status=Artwork.Status.PUBLISHED)
        fav = ArtworkFavorite.objects.filter(user=request.user, artwork=artwork).first()
        if fav:
            fav.delete()
            favorited = False
        else:
            ArtworkFavorite.objects.create(user=request.user, artwork=artwork)
            favorited = True

        return Response({
            'favorited': favorited,
            'favorite_count': artwork.favorite_count,
            'artwork_id': artwork.id
        })


class MyFavoritesListView(generics.ListAPIView):
    """
    List artworks favorited by current user.
    Only PUBLISHED artworks are returned.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PublicArtworkListSerializer

    def get_queryset(self):
        from .models import ArtworkFavorite
        return Artwork.objects.filter(
            favorited_by__user=self.request.user,
            status=Artwork.Status.PUBLISHED
        ).select_related('creator', 'creator__artist_profile', 'category').prefetch_related('tags', 'license_options').order_by('-favorited_by__created_at')


class MyFavoriteIdsView(APIView):
    """
    List of artwork IDs favorited by current user.
    Returns empty list if unauthenticated guest.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        if not request.user.is_authenticated:
            return Response({'favorite_ids': []})
        from .models import ArtworkFavorite
        ids = list(ArtworkFavorite.objects.filter(user=request.user).values_list('artwork_id', flat=True))
        return Response({'favorite_ids': ids})

