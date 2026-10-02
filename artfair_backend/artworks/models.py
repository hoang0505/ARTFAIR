import os
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.core.validators import MinValueValidator
from django.utils.text import slugify

# Private storage for original deliverables - NEVER served via MEDIA_URL!
protected_storage = FileSystemStorage(
    location=str(settings.PROTECTED_MEDIA_ROOT),
    base_url=None
)


class Category(models.Model):
    """
    Art category classification.
    """
    name = models.CharField('Tên danh mục', max_length=100, unique=True)
    slug = models.SlugField('Slug', max_length=120, unique=True)
    description = models.TextField('Mô tả', blank=True, default='')
    created_at = models.DateTimeField('Ngày tạo', auto_now_add=True)

    class Meta:
        verbose_name = 'Danh mục'
        verbose_name_plural = 'Danh mục'
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Tag(models.Model):
    """
    Artwork tag.
    """
    name = models.CharField('Tên tag', max_length=50, unique=True)
    slug = models.SlugField('Slug', max_length=60, unique=True)
    created_at = models.DateTimeField('Ngày tạo', auto_now_add=True)

    class Meta:
        verbose_name = 'Thẻ (Tag)'
        verbose_name_plural = 'Thẻ (Tags)'
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"#{self.name}"


class Artwork(models.Model):
    """
    Artwork entity.
    Owned by a Creator.
    Can be purchased non-exclusively by multiple buyers (never marked SOLD).
    """
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Bản nháp'
        PUBLISHED = 'PUBLISHED', 'Đã phát hành'
        ARCHIVED = 'ARCHIVED', 'Đã lưu trữ'

    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='artworks',
        verbose_name='Nghệ sĩ sở hữu',
        limit_choices_to={'role': 'CREATOR'}
    )
    title = models.CharField('Tiêu đề tác phẩm', max_length=200)
    slug = models.SlugField('Slug định danh', max_length=250, unique=True)
    description = models.TextField('Mô tả tác phẩm', blank=True, default='')
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='artworks',
        verbose_name='Danh mục'
    )
    tags = models.ManyToManyField(
        Tag,
        blank=True,
        related_name='artworks',
        verbose_name='Thẻ (Tags)'
    )
    style = models.CharField(
        'Phong cách nghệ thuật',
        max_length=50,
        blank=True,
        default='',
        help_text='Ví dụ: Sơn dầu, Phục hưng, Tối giản, Anime, Digital Painting, Thủy mặc, Concept Art...'
    )
    preview_image = models.ImageField(
        'Ảnh xem trước (đã đóng watermark)',
        upload_to='previews/%Y/%m/',
        blank=True,
        null=True,
        help_text='Ảnh xem trước chất lượng trung bình, đã chèn watermark để bảo vệ bản quyền.'
    )
    status = models.CharField(
        'Trạng thái',
        max_length=15,
        choices=Status.choices,
        default=Status.DRAFT
    )
    created_at = models.DateTimeField('Ngày tạo', auto_now_add=True)
    updated_at = models.DateTimeField('Cập nhật lần cuối', auto_now=True)

    class Meta:
        verbose_name = 'Tác phẩm nghệ thuật'
        verbose_name_plural = 'Tác phẩm nghệ thuật'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title) or 'artwork'
            candidate_slug = base_slug
            counter = 1
            while Artwork.objects.filter(slug=candidate_slug).exclude(pk=self.pk).exists():
                candidate_slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = candidate_slug
        super().save(*args, **kwargs)

    def can_be_published(self):
        """
        Check if artwork fulfills all criteria to be published:
        1. Must have preview image.
        2. Must have original file.
        3. Must have valid active PERSONAL license option with price > 0.
        4. Must have valid active COMMERCIAL license option with price > 0.
        Returns: (is_eligible: bool, error_messages: list[str])
        """
        errors = []
        if not self.preview_image:
            errors.append("Tác phẩm chưa có ảnh xem trước (preview).")

        has_file = False
        try:
            if self.original_file and self.original_file.file:
                has_file = True
        except Exception:
            has_file = False

        if not has_file:
            errors.append("Tác phẩm chưa có tệp gốc bàn giao (ArtworkFile).")

        # Check license options
        active_licenses = {
            opt.license_type: opt
            for opt in self.license_options.filter(is_active=True)
        }

        if LicenseOption.LicenseType.PERSONAL not in active_licenses:
            errors.append("Thiếu gói quyền sử dụng cá nhân (PERSONAL) đang hoạt động.")
        else:
            personal_lic = active_licenses[LicenseOption.LicenseType.PERSONAL]
            if personal_lic.price <= Decimal('0'):
                errors.append("Giá gói quyền PERSONAL phải lớn hơn 0 VND.")

        if LicenseOption.LicenseType.COMMERCIAL not in active_licenses:
            errors.append("Thiếu gói quyền sử dụng thương mại (COMMERCIAL) đang hoạt động.")
        else:
            comm_lic = active_licenses[LicenseOption.LicenseType.COMMERCIAL]
            if comm_lic.price <= Decimal('0'):
                errors.append("Giá gói quyền COMMERCIAL phải lớn hơn 0 VND.")

        return len(errors) == 0, errors

    @property
    def favorite_count(self):
        return self.favorited_by.count()

    def __str__(self):
        return f"{self.title} - @{self.creator.username} [{self.get_status_display()}]"


class ArtworkFile(models.Model):
    """
    Original master/delivery file of the artwork.
    Stored securely in private protected storage.
    NEVER accessible via public MEDIA_URL!
    """
    artwork = models.OneToOneField(
        Artwork,
        on_delete=models.CASCADE,
        related_name='original_file',
        verbose_name='Tác phẩm'
    )
    file = models.FileField(
        'Tệp bàn giao gốc',
        storage=protected_storage,
        upload_to='original_files/%Y/%m/'
    )
    original_filename = models.CharField('Tên tệp gốc', max_length=255)
    file_format = models.CharField('Định dạng tệp', max_length=30)
    file_size_bytes = models.BigIntegerField('Dung lượng (bytes)')
    width = models.PositiveIntegerField('Chiều rộng (pixels)', null=True, blank=True)
    height = models.PositiveIntegerField('Chiều cao (pixels)', null=True, blank=True)
    dpi = models.PositiveIntegerField('Độ phân giải DPI', null=True, blank=True)
    color_mode = models.CharField('Hệ màu', max_length=30, blank=True, default='')
    created_at = models.DateTimeField('Ngày tải lên', auto_now_add=True)
    updated_at = models.DateTimeField('Cập nhật lần cuối', auto_now=True)

    class Meta:
        verbose_name = 'Tệp gốc tác phẩm'
        verbose_name_plural = 'Tệp gốc tác phẩm'

    def __str__(self):
        return f"File: {self.original_filename} ({self.file_format}) - {self.artwork.title}"


class LicenseOption(models.Model):
    """
    License tier for artwork: PERSONAL or COMMERCIAL.
    Each artwork must have only one option per license type.
    """
    class LicenseType(models.TextChoices):
        PERSONAL = 'PERSONAL', 'Sử dụng cá nhân (Personal)'
        COMMERCIAL = 'COMMERCIAL', 'Sử dụng thương mại (Commercial)'

    artwork = models.ForeignKey(
        Artwork,
        on_delete=models.CASCADE,
        related_name='license_options',
        verbose_name='Tác phẩm'
    )
    license_type = models.CharField(
        'Loại quyền sử dụng',
        max_length=20,
        choices=LicenseType.choices
    )
    price = models.DecimalField(
        'Giá bán (VND)',
        max_digits=12,
        decimal_places=0,
        validators=[MinValueValidator(Decimal('1000'))],
        help_text='Giá bán tối thiểu từ 1,000 VND trở lên.'
    )
    terms = models.TextField('Điều khoản sử dụng', blank=True, default='')
    is_active = models.BooleanField('Đang áp dụng', default=True)
    created_at = models.DateTimeField('Ngày tạo', auto_now_add=True)
    updated_at = models.DateTimeField('Cập nhật lần cuối', auto_now=True)

    class Meta:
        verbose_name = 'Gói quyền sử dụng'
        verbose_name_plural = 'Các gói quyền sử dụng'
        constraints = [
            models.UniqueConstraint(
                fields=['artwork', 'license_type'],
                name='unique_artwork_license_type'
            )
        ]
        ordering = ['license_type']

    def __str__(self):
        return f"{self.get_license_type_display()}: {int(self.price):,} VND ({self.artwork.title})"


class Order(models.Model):
    """
    Purchase order for an artwork license tier.
    Stores buyer, artwork, license type, snapshot price, terms at purchase time, and status.
    """
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Chờ thanh toán'
        COMPLETED = 'COMPLETED', 'Đã thanh toán (Thành công)'
        FAILED = 'FAILED', 'Thanh toán thất bại'
        CANCELLED = 'CANCELLED', 'Đã hủy'

    order_code = models.CharField('Mã đơn hàng', max_length=50, unique=True, editable=False)
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='orders',
        verbose_name='Người mua'
    )
    artwork = models.ForeignKey(
        Artwork,
        on_delete=models.CASCADE,
        related_name='orders',
        verbose_name='Tác phẩm'
    )
    license_type = models.CharField(
        'Loại quyền sử dụng',
        max_length=20,
        choices=LicenseOption.LicenseType.choices
    )
    license_option = models.ForeignKey(
        LicenseOption,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders',
        verbose_name='Gói quyền'
    )
    price_paid = models.DecimalField(
        'Số tiền (VND)',
        max_digits=12,
        decimal_places=0,
        help_text='Giá tiền được hệ thống xác thực và cố định tại thời điểm tạo đơn.'
    )
    terms_snapshot = models.TextField('Điều khoản tại thời điểm mua', blank=True, default='')
    status = models.CharField(
        'Trạng thái đơn hàng',
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    created_at = models.DateTimeField('Ngày tạo đơn', auto_now_add=True)
    completed_at = models.DateTimeField('Thời điểm thanh toán', null=True, blank=True)

    class Meta:
        verbose_name = 'Đơn mua quyền sử dụng'
        verbose_name_plural = 'Danh sách đơn mua'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.order_code:
            import uuid
            from django.utils import timezone
            date_str = timezone.now().strftime('%Y%m%d')
            unique_part = uuid.uuid4().hex[:6].upper()
            self.order_code = f"AF-{date_str}-{unique_part}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order_code} - {self.buyer.username} [{self.get_status_display()}]"


class Withdrawal(models.Model):
    """
    Simulated payout / withdrawal request for artwork sales revenue.
    Creator can request withdrawal up to their current available balance.
    Transactions are handled atomically without real money transfers.
    """
    class Status(models.TextChoices):
        COMPLETED = 'COMPLETED', 'Đã giải ngân (Mô phỏng)'
        PROCESSING = 'PROCESSING', 'Đang xử lý (Mô phỏng)'
        REJECTED = 'REJECTED', 'Từ chối'

    withdrawal_code = models.CharField('Mã rút tiền', max_length=50, unique=True, editable=False)
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='withdrawals',
        verbose_name='Nghệ sĩ'
    )
    amount = models.DecimalField(
        'Số tiền rút (VND)',
        max_digits=12,
        decimal_places=0,
        validators=[MinValueValidator(Decimal('1000'))]
    )
    status = models.CharField(
        'Trạng thái',
        max_length=20,
        choices=Status.choices,
        default=Status.COMPLETED
    )
    note = models.CharField('Ghi chú giao dịch', max_length=255, blank=True, default='Rút doanh thu bán quyền sử dụng tác phẩm (Mô phỏng)')
    created_at = models.DateTimeField('Thời điểm tạo', auto_now_add=True)

    class Meta:
        verbose_name = 'Yêu cầu rút tiền mô phỏng'
        verbose_name_plural = 'Danh sách rút tiền mô phỏng'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.withdrawal_code:
            import uuid
            from django.utils import timezone
            date_str = timezone.now().strftime('%Y%m%d')
            unique_part = uuid.uuid4().hex[:6].upper()
            self.withdrawal_code = f"WD-{date_str}-{unique_part}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.withdrawal_code} - {self.creator.username} [{int(self.amount):,} VND] - {self.get_status_display()}"


class ArtworkFavorite(models.Model):
    """
    User's favorited artworks (Wishlist).
    Saved per user with unique constraint to prevent duplicates.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='favorites',
        verbose_name='Người dùng'
    )
    artwork = models.ForeignKey(
        Artwork,
        on_delete=models.CASCADE,
        related_name='favorited_by',
        verbose_name='Tác phẩm'
    )
    created_at = models.DateTimeField('Thời điểm yêu thích', auto_now_add=True)

    class Meta:
        verbose_name = 'Tác phẩm yêu thích'
        verbose_name_plural = 'Danh sách tác phẩm yêu thích'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'artwork'],
                name='unique_user_artwork_favorite'
            )
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"@{self.user.username} ❤️ {self.artwork.title}"


def get_creator_financials(creator_user):
    """
    Computes total sales revenue, total withdrawn, and available balance for a creator.
    Only COMPLETED orders count toward revenue.
    Only COMPLETED or PROCESSING withdrawals count toward withdrawn amounts.
    Platform fee is 0% in initial phase.
    """
    from django.db.models import Sum

    artwork_revenue = Order.objects.filter(
        artwork__creator=creator_user,
        status=Order.Status.COMPLETED
    ).aggregate(total=Sum('price_paid'))['total'] or Decimal('0')

    commission_revenue = Decimal('0')
    try:
        from commissions.models import Commission
        commission_revenue = Commission.objects.filter(
            creator=creator_user,
            status=Commission.Status.COMPLETED,
            is_escrow_released=True
        ).aggregate(total=Sum('agreed_price'))['total'] or Decimal('0')
    except Exception:
        commission_revenue = Decimal('0')

    total_revenue = artwork_revenue + commission_revenue

    total_withdrawn = Withdrawal.objects.filter(
        creator=creator_user,
        status__in=[Withdrawal.Status.COMPLETED, Withdrawal.Status.PROCESSING]
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    available_balance = total_revenue - total_withdrawn
    if available_balance < Decimal('0'):
        available_balance = Decimal('0')

    return {
        'total_revenue': total_revenue,
        'artwork_revenue': artwork_revenue,
        'commission_revenue': commission_revenue,
        'total_withdrawn': total_withdrawn,
        'available_balance': available_balance,
    }
