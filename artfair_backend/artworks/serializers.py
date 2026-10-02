from decimal import Decimal
from rest_framework import serializers
from .models import Category, Tag, Artwork, ArtworkFile, LicenseOption, Order, Withdrawal
from .utils import (
    ALLOWED_ORIGINAL_EXTENSIONS,
    ALLOWED_PREVIEW_EXTENSIONS,
    validate_file_size,
    validate_file_extension,
    extract_metadata_and_inspect,
    generate_watermarked_preview,
)


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ('id', 'name', 'slug', 'description')


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ('id', 'name', 'slug')


class LicenseOptionSerializer(serializers.ModelSerializer):
    price = serializers.DecimalField(max_digits=12, decimal_places=0, min_value=Decimal('1000'))

    class Meta:
        model = LicenseOption
        fields = ('id', 'license_type', 'price', 'terms', 'is_active', 'updated_at')
        read_only_fields = ('id', 'updated_at')


class ArtworkFileMetadataSerializer(serializers.ModelSerializer):
    """
    Metadata serializer for artwork original file.
    Does NOT expose raw file system path or unprotected URLs.
    Includes an authenticated download URL.
    """
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = ArtworkFile
        fields = (
            'id',
            'original_filename',
            'file_format',
            'file_size_bytes',
            'width',
            'height',
            'dpi',
            'color_mode',
            'download_url',
            'created_at',
        )
        read_only_fields = fields

    def get_download_url(self, obj):
        request = self.context.get('request')
        endpoint = f"/api/artworks/{obj.artwork_id}/download-file/"
        if request:
            return request.build_absolute_uri(endpoint)
        return endpoint


class CreatorSummarySerializer(serializers.Serializer):
    username = serializers.CharField()
    display_name = serializers.SerializerMethodField()

    def get_display_name(self, user):
        if hasattr(user, 'artist_profile'):
            return user.artist_profile.display_name
        return user.username


class PublicArtworkListSerializer(serializers.ModelSerializer):
    creator = CreatorSummarySerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    license_options = serializers.SerializerMethodField()

    class Meta:
        model = Artwork
        fields = (
            'id',
            'title',
            'slug',
            'creator',
            'category',
            'tags',
            'preview_image',
            'status',
            'created_at',
            'license_options',
        )

    def get_license_options(self, obj):
        active_options = obj.license_options.filter(is_active=True)
        return LicenseOptionSerializer(active_options, many=True).data


class PublicArtworkDetailSerializer(serializers.ModelSerializer):
    creator = CreatorSummarySerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    license_options = serializers.SerializerMethodField()
    file_metadata = serializers.SerializerMethodField()
    user_ownership = serializers.SerializerMethodField()

    class Meta:
        model = Artwork
        fields = (
            'id',
            'title',
            'slug',
            'description',
            'creator',
            'category',
            'tags',
            'preview_image',
            'status',
            'created_at',
            'updated_at',
            'license_options',
            'file_metadata',
            'user_ownership',
        )

    def get_license_options(self, obj):
        active_options = obj.license_options.filter(is_active=True)
        return LicenseOptionSerializer(active_options, many=True).data

    def get_file_metadata(self, obj):
        # Expose non-sensitive delivery file metadata (DPI, resolution, format)
        if hasattr(obj, 'original_file') and obj.original_file:
            f = obj.original_file
            return {
                'file_format': f.file_format,
                'width': f.width,
                'height': f.height,
                'dpi': f.dpi,
                'color_mode': f.color_mode,
            }
        return None

    def get_user_ownership(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return []
        return list(
            Order.objects.filter(
                buyer=request.user,
                artwork=obj,
                status=Order.Status.COMPLETED
            ).values_list('license_type', flat=True)
        )



class CreatorArtworkSerializer(serializers.ModelSerializer):
    """
    Serializer used by Creator to view, create, and edit their artworks.
    Automatically assigns creator from request.user; ignores owner_id in payload.
    """
    creator = CreatorSummarySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        source='category',
        write_only=True
    )
    category = CategorySerializer(read_only=True)
    tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=Tag.objects.all(),
        many=True,
        source='tags',
        required=False
    )
    tags = TagSerializer(many=True, read_only=True)
    original_file = ArtworkFileMetadataSerializer(read_only=True)
    license_options = LicenseOptionSerializer(many=True, read_only=True)
    publishing_eligibility = serializers.SerializerMethodField()
    completed_orders_count = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Artwork
        fields = (
            'id',
            'title',
            'slug',
            'description',
            'creator',
            'category_id',
            'category',
            'tag_ids',
            'tags',
            'preview_image',
            'status',
            'status_display',
            'original_file',
            'license_options',
            'publishing_eligibility',
            'completed_orders_count',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'slug', 'creator', 'status', 'created_at', 'updated_at')

    def get_completed_orders_count(self, obj):
        return getattr(obj, 'completed_orders_count', None) or obj.orders.filter(status=Order.Status.COMPLETED).count()

    def get_publishing_eligibility(self, obj):
        is_ready, reasons = obj.can_be_published()
        return {
            'can_publish': is_ready,
            'blocking_reasons': reasons
        }

    def create(self, validated_data):
        # Creator is ALWAYS taken from request context
        user = self.context['request'].user
        validated_data['creator'] = user
        return super().create(validated_data)


class UploadArtworkFileSerializer(serializers.Serializer):
    """
    Serializer for uploading original master file and optional custom preview.
    Handles watermark preview generation and format/size checks.
    """
    file = serializers.FileField(required=True)
    preview_image = serializers.ImageField(required=False, allow_null=True)

    def validate_file(self, value):
        validate_file_size(value, label="tệp bàn giao gốc")
        validate_file_extension(value.name, ALLOWED_ORIGINAL_EXTENSIONS)
        return value

    def validate_preview_image(self, value):
        if value:
            validate_file_size(value, max_mb=10, label="ảnh xem trước")
            validate_file_extension(value.name, ALLOWED_PREVIEW_EXTENSIONS)
        return value


class OrderArtworkSummarySerializer(serializers.ModelSerializer):
    creator_name = serializers.SerializerMethodField()

    class Meta:
        model = Artwork
        fields = ('id', 'title', 'slug', 'preview_image', 'creator_name')

    def get_creator_name(self, obj):
        if hasattr(obj.creator, 'artist_profile'):
            return obj.creator.artist_profile.display_name
        return obj.creator.username


class OrderSerializer(serializers.ModelSerializer):
    buyer_username = serializers.CharField(source='buyer.username', read_only=True)
    artwork = OrderArtworkSummarySerializer(read_only=True)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            'id',
            'order_code',
            'buyer_username',
            'artwork',
            'license_type',
            'price_paid',
            'terms_snapshot',
            'status',
            'download_url',
            'created_at',
            'completed_at',
        )
        read_only_fields = fields

    def get_download_url(self, obj):
        if obj.status == Order.Status.COMPLETED:
            request = self.context.get('request')
            endpoint = f"/api/artworks/{obj.artwork_id}/download-file/"
            if request:
                return request.build_absolute_uri(endpoint)
            return endpoint
        return None


class CreateOrderSerializer(serializers.Serializer):
    artwork_id = serializers.IntegerField(required=True)
    license_type = serializers.ChoiceField(choices=LicenseOption.LicenseType.choices, required=True)

    def validate(self, attrs):
        user = self.context['request'].user
        artwork_id = attrs['artwork_id']
        license_type = attrs['license_type']

        try:
            artwork = Artwork.objects.get(pk=artwork_id, status=Artwork.Status.PUBLISHED)
        except Artwork.DoesNotExist:
            raise serializers.ValidationError({'artwork_id': 'Tác phẩm không tồn tại hoặc chưa được phát hành.'})

        if artwork.creator == user:
            raise serializers.ValidationError({'detail': 'Nghệ sĩ không thể tự mua quyền sử dụng tác phẩm của chính mình.'})

        license_option = artwork.license_options.filter(license_type=license_type, is_active=True).first()
        if not license_option:
            raise serializers.ValidationError({'license_type': 'Gói quyền sử dụng này hiện không khả dụng cho tác phẩm.'})

        already_owned = Order.objects.filter(
            buyer=user,
            artwork=artwork,
            license_type=license_type,
            status=Order.Status.COMPLETED
        ).exists()
        if already_owned:
            raise serializers.ValidationError({
                'detail': f'Bạn đã sở hữu gói quyền {license_type} của tác phẩm này.',
                'already_owned': True,
                'license_type': license_type
            })

        attrs['artwork'] = artwork
        attrs['license_option'] = license_option
        return attrs

    def create(self, validated_data):
        user = self.context['request'].user
        artwork = validated_data['artwork']
        license_option = validated_data['license_option']
        license_type = validated_data['license_type']

        order = Order.objects.create(
            buyer=user,
            artwork=artwork,
            license_type=license_type,
            license_option=license_option,
            price_paid=license_option.price,  # 100% backend-enforced price
            terms_snapshot=license_option.terms,
            status=Order.Status.PENDING
        )
        return order



class PurchasedArtworkLibrarySerializer(serializers.ModelSerializer):
    """
    Serializer for buyer's personal artwork library (Screen 04).
    Displays artworks granted from completed orders, distinct per license tier.
    """
    order_code = serializers.CharField(read_only=True)
    artwork_id = serializers.IntegerField(source='artwork.id', read_only=True)
    artwork_title = serializers.CharField(source='artwork.title', read_only=True)
    artwork_slug = serializers.CharField(source='artwork.slug', read_only=True)
    artist_username = serializers.CharField(source='artwork.creator.username', read_only=True)
    artist_display_name = serializers.SerializerMethodField()
    preview_image = serializers.SerializerMethodField()
    license_name = serializers.CharField(source='get_license_type_display', read_only=True)
    purchase_date = serializers.DateTimeField(source='completed_at', read_only=True)
    has_original_file = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()
    certificate_url = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            'id',
            'order_code',
            'artwork_id',
            'artwork_title',
            'artwork_slug',
            'artist_username',
            'artist_display_name',
            'preview_image',
            'license_type',
            'license_name',
            'price_paid',
            'terms_snapshot',
            'purchase_date',
            'has_original_file',
            'download_url',
            'certificate_url',
        )

    def get_artist_display_name(self, obj):
        creator = obj.artwork.creator
        if hasattr(creator, 'artist_profile') and creator.artist_profile and creator.artist_profile.display_name:
            return creator.artist_profile.display_name
        return creator.username

    def get_preview_image(self, obj):
        if obj.artwork.preview_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.artwork.preview_image.url)
            return obj.artwork.preview_image.url
        return None

    def get_has_original_file(self, obj):
        return bool(hasattr(obj.artwork, 'original_file') and obj.artwork.original_file.file)

    def get_download_url(self, obj):
        return f"/api/artworks/{obj.artwork.id}/download-file/"

    def get_certificate_url(self, obj):
        return f"/api/artworks/orders/{obj.order_code}/certificate/"


class WithdrawalSerializer(serializers.ModelSerializer):
    """
    Serializer for displaying simulated withdrawal records.
    """
    creator_username = serializers.CharField(source='creator.username', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Withdrawal
        fields = (
            'id',
            'withdrawal_code',
            'creator_username',
            'amount',
            'status',
            'status_display',
            'note',
            'created_at',
        )
        read_only_fields = ('id', 'withdrawal_code', 'creator_username', 'status', 'created_at')


class CreateWithdrawalSerializer(serializers.Serializer):
    """
    Serializer for creating simulated withdrawal requests.
    Validates amount > 0 and format.
    """
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=0,
        min_value=Decimal('1000'),
        help_text='S? ti?n r?t (VND, t?i thi?u 1,000 VND)'
    )
    note = serializers.CharField(
        max_length=255,
        required=False,
        default='R?t doanh thu b?n quy?n s? d?ng t?c ph?m (M? ph?ng)'
    )
