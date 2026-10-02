import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.core.validators import MinValueValidator
from django.utils import timezone

protected_storage = FileSystemStorage(
    location=str(settings.PROTECTED_MEDIA_ROOT),
    base_url=None
)


class Commission(models.Model):
    """
    Commission entity for custom artwork orders between a Buyer and a Creator.
    Workflow:
      REQUESTED -> QUOTED -> (Accept & Simulated Payment) -> IN_PROGRESS -> DELIVERED -> COMPLETED
      (With possible REVISION_REQUESTED, REJECTED, or CANCELLED transitions)
    """
    class LicenseType(models.TextChoices):
        PERSONAL = 'PERSONAL', 'Sử dụng cá nhân (Personal)'
        COMMERCIAL = 'COMMERCIAL', 'Sử dụng thương mại (Commercial)'

    class Status(models.TextChoices):
        REQUESTED = 'REQUESTED', 'Chờ nghệ sĩ phản hồi'
        QUOTED = 'QUOTED', 'Đã báo giá / Chờ duyệt'
        IN_PROGRESS = 'IN_PROGRESS', 'Đang thực hiện'
        DELIVERED = 'DELIVERED', 'Đã bàn giao / Chờ nghiệm thu'
        REVISION_REQUESTED = 'REVISION_REQUESTED', 'Yêu cầu chỉnh sửa'
        COMPLETED = 'COMPLETED', 'Hoàn tất / Đã giải ngân'
        REJECTED = 'REJECTED', 'Nghệ sĩ từ chối'
        CANCELLED = 'CANCELLED', 'Đã hủy'

    commission_code = models.CharField('Mã đặt vẽ', max_length=50, unique=True, editable=False)
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='buyer_commissions',
        verbose_name='Người mua (Buyer)'
    )
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='creator_commissions',
        verbose_name='Nghệ sĩ nhận vẽ (Creator)',
        limit_choices_to={'role': 'CREATOR'}
    )
    title = models.CharField('Tiêu đề yêu cầu', max_length=200)
    description = models.TextField('Mô tả ý tưởng / Brief')
    license_type = models.CharField(
        'Loại quyền sử dụng',
        max_length=20,
        choices=LicenseType.choices,
        default=LicenseType.PERSONAL
    )
    budget = models.DecimalField(
        'Ngân sách dự kiến (VND)',
        max_digits=12,
        decimal_places=0,
        validators=[MinValueValidator(Decimal('1000'))]
    )
    deadline = models.DateField('Hạn mong muốn hoàn thành')

    # Private Reference / Moodboard file (Stored safely in protected_media)
    reference_image = models.FileField(
        'Tệp tham khảo / Moodboard',
        storage=protected_storage,
        upload_to='commissions/references/%Y/%m/',
        null=True,
        blank=True
    )
    reference_filename = models.CharField('Tên tệp tham khảo', max_length=255, blank=True, default='')
    reference_size_bytes = models.BigIntegerField('Dung lượng tệp tham khảo (bytes)', null=True, blank=True)

    # State
    status = models.CharField(
        'Trạng thái',
        max_length=25,
        choices=Status.choices,
        default=Status.REQUESTED
    )

    # Agreed snapshot details (Set when Buyer accepts a quote)
    agreed_price = models.DecimalField(
        'Giá đã chốt (VND)',
        max_digits=12,
        decimal_places=0,
        null=True,
        blank=True
    )
    agreed_delivery_date = models.DateField('Hạn bàn giao đã chốt', null=True, blank=True)
    agreed_scope = models.TextField('Phạm vi công việc đã chốt', blank=True, default='')
    agreed_terms = models.TextField('Điều khoản quyền đã chốt', blank=True, default='')
    agreed_max_revisions = models.PositiveIntegerField('Số lần chỉnh sửa cho phép', default=1)
    revisions_used = models.PositiveIntegerField('Số lần đã yêu cầu chỉnh sửa', default=0)

    # Payment & Escrow flags
    is_paid = models.BooleanField('Đã thanh toán mô phỏng (Ký quỹ)', default=False)
    paid_at = models.DateTimeField('Thời điểm thanh toán', null=True, blank=True)
    is_escrow_released = models.BooleanField('Đã giải ngân doanh thu cho nghệ sĩ', default=False)
    completed_at = models.DateTimeField('Thời điểm hoàn tất', null=True, blank=True)

    # Rejection & Cancellation
    rejection_reason = models.TextField('Lý do nghệ sĩ từ chối', blank=True, default='')
    cancellation_reason = models.TextField('Lý do hủy đơn', blank=True, default='')

    # Work in progress sketches
    sketch_file = models.FileField(
        'Phác thảo tiến độ',
        storage=protected_storage,
        upload_to='commissions/sketches/%Y/%m/',
        null=True,
        blank=True
    )
    sketch_filename = models.CharField('Tên tệp phác thảo', max_length=255, blank=True, default='')

    # Final deliverables
    final_delivery_file = models.FileField(
        'Tệp bàn giao hoàn chỉnh',
        storage=protected_storage,
        upload_to='commissions/deliverables/%Y/%m/',
        null=True,
        blank=True
    )
    final_delivery_filename = models.CharField('Tên tệp bàn giao', max_length=255, blank=True, default='')
    final_delivery_size_bytes = models.BigIntegerField('Dung lượng tệp bàn giao (bytes)', null=True, blank=True)
    final_delivery_note = models.TextField('Ghi chú bàn giao', blank=True, default='')

    created_at = models.DateTimeField('Ngày tạo yêu cầu', auto_now_add=True)
    updated_at = models.DateTimeField('Cập nhật lần cuối', auto_now=True)

    class Meta:
        verbose_name = 'Đơn đặt vẽ (Commission)'
        verbose_name_plural = 'Danh sách đặt vẽ (Commissions)'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.commission_code:
            date_str = timezone.now().strftime('%Y%m%d')
            unique_part = uuid.uuid4().hex[:6].upper()
            self.commission_code = f"CMS-{date_str}-{unique_part}"
        super().save(*args, **kwargs)

    @property
    def latest_proposal(self):
        return self.proposals.order_by('-version').first()

    @property
    def active_proposal(self):
        return self.proposals.filter(status=CommissionProposal.Status.PENDING).order_by('-version').first()

    @property
    def accepted_proposal(self):
        return self.proposals.filter(status=CommissionProposal.Status.ACCEPTED).first()

    @property
    def remaining_revisions(self):
        return max(0, self.agreed_max_revisions - self.revisions_used)

    def __str__(self):
        return f"{self.commission_code} - {self.title} (@{self.buyer.username} -> @{self.creator.username}) [{self.get_status_display()}]"


class CommissionProposal(models.Model):
    """
    Official quote / proposal submitted by the Creator.
    Allows versioning when quotes are modified.
    """
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Chờ người mua duyệt'
        ACCEPTED = 'ACCEPTED', 'Đã chấp nhận'
        REJECTED = 'REJECTED', 'Người mua từ chối'
        SUPERSEDED = 'SUPERSEDED', 'Đã thay thế bằng báo giá mới'

    commission = models.ForeignKey(
        Commission,
        on_delete=models.CASCADE,
        related_name='proposals',
        verbose_name='Đơn đặt vẽ'
    )
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='commission_proposals',
        verbose_name='Nghệ sĩ báo giá'
    )
    version = models.PositiveIntegerField('Phiên bản báo giá', default=1)
    price = models.DecimalField(
        'Báo giá chính thức (VND)',
        max_digits=12,
        decimal_places=0,
        validators=[MinValueValidator(Decimal('1000'))]
    )
    delivery_date = models.DateField('Hạn dự kiến bàn giao')
    scope_of_work = models.TextField('Phạm vi công việc')
    max_revisions = models.PositiveIntegerField('Số lần chỉnh sửa cho phép', default=1)
    license_terms = models.TextField('Điều khoản quyền sử dụng', blank=True, default='')

    sketch_file = models.FileField(
        'Bản phác thảo đính kèm (nếu có)',
        storage=protected_storage,
        upload_to='commissions/proposals/%Y/%m/',
        null=True,
        blank=True
    )

    status = models.CharField(
        'Trạng thái báo giá',
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    created_at = models.DateTimeField('Thời điểm gửi báo giá', auto_now_add=True)

    class Meta:
        verbose_name = 'Báo giá Commission'
        verbose_name_plural = 'Danh sách báo giá Commission'
        ordering = ['-version']
        constraints = [
            models.UniqueConstraint(
                fields=['commission', 'version'],
                name='unique_commission_proposal_version'
            )
        ]

    def __str__(self):
        return f"{self.commission.commission_code} v{self.version}: {int(self.price):,} VND [{self.get_status_display()}]"


class CommissionEvent(models.Model):
    """
    Event log & timeline for transparency and tracking.
    """
    class EventType(models.TextChoices):
        REQUEST_CREATED = 'REQUEST_CREATED', 'Tạo yêu cầu đặt vẽ'
        PROPOSAL_SENT = 'PROPOSAL_SENT', 'Nghệ sĩ gửi báo giá'
        PROPOSAL_REJECTED = 'PROPOSAL_REJECTED', 'Người mua từ chối báo giá'
        PAYMENT_COMPLETED = 'PAYMENT_COMPLETED', 'Thanh toán mô phỏng (Ký quỹ)'
        SKETCH_UPLOADED = 'SKETCH_UPLOADED', 'Tải lên phác thảo'
        DELIVERED = 'DELIVERED', 'Bàn giao tác phẩm'
        REVISION_REQUESTED = 'REVISION_REQUESTED', 'Yêu cầu chỉnh sửa'
        COMPLETED = 'COMPLETED', 'Nghiệm thu hoàn tất'
        REJECTED = 'REJECTED', 'Nghệ sĩ từ chối yêu cầu'
        CANCELLED = 'CANCELLED', 'Hủy yêu cầu'

    commission = models.ForeignKey(
        Commission,
        on_delete=models.CASCADE,
        related_name='events',
        verbose_name='Đơn đặt vẽ'
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='commission_actions',
        verbose_name='Người thực hiện'
    )
    event_type = models.CharField('Loại sự kiện', max_length=30, choices=EventType.choices)
    title = models.CharField('Tiêu đề sự kiện', max_length=150)
    note = models.TextField('Chi tiết sự kiện', blank=True, default='')
    created_at = models.DateTimeField('Thời điểm diễn ra', auto_now_add=True)

    class Meta:
        verbose_name = 'Lịch sử sự kiện Commission'
        verbose_name_plural = 'Lịch sử sự kiện Commission'
        ordering = ['created_at']

    def __str__(self):
        return f"[{self.created_at.strftime('%d/%m/%Y %H:%M')}] {self.commission.commission_code}: {self.title}"
