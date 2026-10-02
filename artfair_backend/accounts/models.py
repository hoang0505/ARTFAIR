from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


class CustomUserManager(UserManager):
    """
    Custom user manager ensuring email is normalized and unique.
    """
    def create_user(self, username, email=None, password=None, **extra_fields):
        if email:
            email = self.normalize_email(email)
        return super().create_user(username, email=email, password=password, **extra_fields)

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        if email:
            email = self.normalize_email(email)
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', User.Role.CREATOR)
        extra_fields.setdefault('is_email_verified', True)
        return super().create_superuser(username, email=email, password=password, **extra_fields)


class User(AbstractUser):
    """
    Custom User model for ARTFAIR.
    Role: BUYER or CREATOR.
    Creator has all Buyer permissions plus selling / publishing artwork permissions.
    """
    class Role(models.TextChoices):
        BUYER = 'BUYER', 'Người mua (Buyer)'
        CREATOR = 'CREATOR', 'Nghệ sĩ / Nhà sáng tạo (Creator)'

    email = models.EmailField('Địa chỉ email', unique=True)
    role = models.CharField(
        'Vai trò tài khoản',
        max_length=10,
        choices=Role.choices,
        default=Role.BUYER
    )
    is_email_verified = models.BooleanField(
        'Đã xác thực email',
        default=False,
        help_text='Trạng thái xác thực email (chưa dùng để khóa đăng nhập ở bản phát triển này).'
    )

    objects = CustomUserManager()

    @property
    def is_creator(self):
        return self.role == self.Role.CREATOR

    @property
    def is_buyer(self):
        return self.role == self.Role.BUYER

    def clean(self):
        super().clean()
        if self.email:
            self.email = self.__class__.objects.normalize_email(self.email)

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.__class__.objects.normalize_email(self.email)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


from django.core.validators import MinValueValidator, MaxValueValidator


class ArtistProfile(models.Model):
    """
    Artist Profile for Creators.
    Only users with role CREATOR can have an ArtistProfile.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='artist_profile',
        limit_choices_to={'role': User.Role.CREATOR}
    )
    display_name = models.CharField('Bút danh / Tên hiển thị', max_length=100)
    bio = models.TextField('Tiểu sử nghệ sĩ', blank=True, default='')
    avatar = models.ImageField(
        'Ảnh đại diện',
        upload_to='avatars/%Y/%m/',
        blank=True,
        null=True
    )
    cover_image = models.ImageField(
        'Ảnh bìa hồ sơ',
        upload_to='covers/%Y/%m/',
        blank=True,
        null=True
    )
    is_accepting_commissions = models.BooleanField(
        'Đang nhận Commission',
        default=False
    )
    created_at = models.DateTimeField('Ngày tạo', auto_now_add=True)
    updated_at = models.DateTimeField('Cập nhật lần cuối', auto_now=True)

    class Meta:
        verbose_name = 'Hồ sơ nghệ sĩ'
        verbose_name_plural = 'Hồ sơ nghệ sĩ'

    @property
    def average_rating(self):
        res = self.user.received_reviews.aggregate(avg=models.Avg('rating'))['avg']
        return round(float(res), 1) if res is not None else None

    @property
    def review_count(self):
        return self.user.received_reviews.count()

    @property
    def activity_tier(self):
        artworks_count = self.user.artworks.filter(status='PUBLISHED').count()
        orders_count = self.user.artworks.filter(orders__status='COMPLETED').count()
        comm_mgr = getattr(self.user, 'commissions_as_creator', None)
        comm_count = comm_mgr.filter(status='COMPLETED').count() if comm_mgr else 0
        total_sales = orders_count + comm_count
        avg_rating = self.average_rating

        if artworks_count >= 5 and total_sales >= 3 and (avg_rating is None or avg_rating >= 4.0):
            return {
                'name': 'Nghệ sĩ Tiêu biểu',
                'code': 'PRO',
                'badge_class': 'tier-pro',
                'description': 'Đã xuất bản từ 5 tác phẩm và hoàn tất ít nhất 3 giao dịch thành công trên sàn.'
            }
        elif artworks_count >= 2 or total_sales >= 1:
            return {
                'name': 'Nghệ sĩ Năng nổ',
                'code': 'ACTIVE',
                'badge_class': 'tier-active',
                'description': 'Đã xuất bản từ 2 tác phẩm hoặc có giao dịch đầu tiên được nghiệm thu.'
            }
        else:
            return {
                'name': 'Nghệ sĩ Mới',
                'code': 'NEW',
                'badge_class': 'tier-new',
                'description': 'Nghệ sĩ mới tham gia và đã mở Creator Studio trên ARTFAIR.'
            }

    def __str__(self):
        return f"Nghệ sĩ {self.display_name} (@{self.user.username})"


class Notification(models.Model):
    """
    Real-time system notification for Buyers and Creators.
    Triggered by real business events: purchases, commission proposals, payouts, etc.
    """
    class NotificationType(models.TextChoices):
        ORDER_COMPLETED = 'ORDER_COMPLETED', 'Đơn mua hoàn tất'
        CREATOR_SALE = 'CREATOR_SALE', 'Lượt mua tác phẩm mới'
        COMMISSION_REQUESTED = 'COMMISSION_REQUESTED', 'Yêu cầu đặt vẽ mới'
        COMMISSION_PROPOSAL = 'COMMISSION_PROPOSAL', 'Báo giá Commission'
        COMMISSION_PAID = 'COMMISSION_PAID', 'Ký quỹ thành công'
        COMMISSION_DELIVERED = 'COMMISSION_DELIVERED', 'Bàn giao phác thảo/tác phẩm'
        COMMISSION_REVISION = 'COMMISSION_REVISION', 'Yêu cầu chỉnh sửa'
        COMMISSION_COMPLETED = 'COMMISSION_COMPLETED', 'Nghiệm thu hoàn tất'
        WITHDRAWAL_STATUS = 'WITHDRAWAL_STATUS', 'Trạng thái rút tiền'
        SYSTEM = 'SYSTEM', 'Thông báo hệ thống'

    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name='Người nhận'
    )
    title = models.CharField('Tiêu đề thông báo', max_length=200)
    message = models.TextField('Nội dung thông báo')
    notification_type = models.CharField(
        'Loại thông báo',
        max_length=40,
        choices=NotificationType.choices,
        default=NotificationType.SYSTEM
    )
    target_url = models.CharField('Đường dẫn đối tượng', max_length=255, blank=True, default='')
    is_read = models.BooleanField('Đã đọc', default=False)
    reference_id = models.CharField(
        'Mã tham chiếu (chống trùng)',
        max_length=100,
        blank=True,
        default='',
        db_index=True
    )
    created_at = models.DateTimeField('Thời gian tạo', auto_now_add=True)

    class Meta:
        verbose_name = 'Thông báo'
        verbose_name_plural = 'Danh sách thông báo'
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.get_notification_type_display()}] {self.title} -> {self.recipient.username}"


class ArtistReview(models.Model):
    """
    Verified buyer review for an artist.
    Can only be written by a buyer who completed a real purchase order or commission with this artist.
    1 review per transaction; only author can edit.
    """
    artist = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='received_reviews',
        limit_choices_to={'role': User.Role.CREATOR},
        verbose_name='Nghệ sĩ được đánh giá'
    )
    reviewer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='given_reviews',
        verbose_name='Người đánh giá'
    )
    order = models.OneToOneField(
        'artworks.Order',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='review',
        verbose_name='Đơn mua tác phẩm'
    )
    commission = models.OneToOneField(
        'commissions.Commission',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='review',
        verbose_name='Đơn đặt vẽ Commission'
    )
    rating = models.PositiveSmallIntegerField(
        'Điểm đánh giá',
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField('Nhận xét', max_length=1000)
    created_at = models.DateTimeField('Ngày đánh giá', auto_now_add=True)
    updated_at = models.DateTimeField('Cập nhật lần cuối', auto_now=True)

    class Meta:
        verbose_name = 'Đánh giá nghệ sĩ'
        verbose_name_plural = 'Danh sách đánh giá nghệ sĩ'
        ordering = ['-created_at']

    def __str__(self):
        return f"Review by @{self.reviewer.username} for @{self.artist.username} ({self.rating}★)"

