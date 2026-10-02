import os
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Commission, CommissionProposal, CommissionEvent
from artworks.utils import validate_file_size, validate_file_extension, ALLOWED_ORIGINAL_EXTENSIONS, RASTER_EXTENSIONS

User = get_user_model()


class CommissionProposalSerializer(serializers.ModelSerializer):
    creator_name = serializers.SerializerMethodField()
    has_sketch = serializers.SerializerMethodField()
    sketch_download_url = serializers.SerializerMethodField()

    class Meta:
        model = CommissionProposal
        fields = [
            'id',
            'version',
            'price',
            'delivery_date',
            'scope_of_work',
            'max_revisions',
            'license_terms',
            'status',
            'creator_name',
            'has_sketch',
            'sketch_download_url',
            'created_at',
        ]
        read_only_fields = ['id', 'version', 'status', 'created_at']

    def get_creator_name(self, obj):
        if hasattr(obj.creator, 'artist_profile') and obj.creator.artist_profile and obj.creator.artist_profile.display_name:
            return obj.creator.artist_profile.display_name
        return obj.creator.username

    def get_has_sketch(self, obj):
        return bool(obj.sketch_file)

    def get_sketch_download_url(self, obj):
        if obj.sketch_file:
            return f"/api/commissions/{obj.commission_id}/download-proposal-sketch/{obj.id}/"
        return None


class CommissionEventSerializer(serializers.ModelSerializer):
    actor_username = serializers.SerializerMethodField()

    class Meta:
        model = CommissionEvent
        fields = [
            'id',
            'event_type',
            'title',
            'note',
            'actor_username',
            'created_at',
        ]

    def get_actor_username(self, obj):
        if obj.actor:
            return obj.actor.username
        return 'Hệ thống'


class CommissionDetailSerializer(serializers.ModelSerializer):
    buyer_info = serializers.SerializerMethodField()
    creator_info = serializers.SerializerMethodField()
    proposals = CommissionProposalSerializer(many=True, read_only=True)
    events = CommissionEventSerializer(many=True, read_only=True)
    active_proposal = serializers.SerializerMethodField()
    accepted_proposal = serializers.SerializerMethodField()

    has_reference = serializers.SerializerMethodField()
    reference_download_url = serializers.SerializerMethodField()
    has_sketch = serializers.SerializerMethodField()
    sketch_download_url = serializers.SerializerMethodField()
    has_final_delivery = serializers.SerializerMethodField()
    delivery_download_url = serializers.SerializerMethodField()
    certificate_url = serializers.SerializerMethodField()

    user_role_in_commission = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()

    class Meta:
        model = Commission
        fields = [
            'id',
            'commission_code',
            'title',
            'description',
            'license_type',
            'budget',
            'deadline',
            'status',
            'buyer_info',
            'creator_info',
            'proposals',
            'events',
            'active_proposal',
            'accepted_proposal',
            'agreed_price',
            'agreed_delivery_date',
            'agreed_scope',
            'agreed_terms',
            'agreed_max_revisions',
            'revisions_used',
            'remaining_revisions',
            'is_paid',
            'paid_at',
            'is_escrow_released',
            'completed_at',
            'rejection_reason',
            'cancellation_reason',
            'has_reference',
            'reference_filename',
            'reference_size_bytes',
            'reference_download_url',
            'has_sketch',
            'sketch_filename',
            'sketch_download_url',
            'has_final_delivery',
            'final_delivery_filename',
            'final_delivery_size_bytes',
            'final_delivery_note',
            'delivery_download_url',
            'certificate_url',
            'user_role_in_commission',
            'allowed_actions',
            'created_at',
            'updated_at',
        ]

    def get_buyer_info(self, obj):
        buyer = obj.buyer
        return {
            'id': buyer.id,
            'username': buyer.username,
            'display_name': buyer.get_full_name() or buyer.username,
        }

    def get_creator_info(self, obj):
        creator = obj.creator
        display_name = creator.username
        avatar_url = None
        if hasattr(creator, 'artist_profile') and creator.artist_profile:
            profile = creator.artist_profile
            display_name = profile.display_name or creator.username
            if profile.avatar:
                avatar_url = profile.avatar.url
        return {
            'id': creator.id,
            'username': creator.username,
            'display_name': display_name,
            'avatar': avatar_url,
        }

    def get_active_proposal(self, obj):
        active = obj.active_proposal
        if active:
            return CommissionProposalSerializer(active).data
        return None

    def get_accepted_proposal(self, obj):
        accepted = obj.accepted_proposal
        if accepted:
            return CommissionProposalSerializer(accepted).data
        return None

    def get_has_reference(self, obj):
        return bool(obj.reference_image)

    def get_reference_download_url(self, obj):
        if obj.reference_image:
            return f"/api/commissions/{obj.id}/download-reference/"
        return None

    def get_has_sketch(self, obj):
        return bool(obj.sketch_file)

    def get_sketch_download_url(self, obj):
        if obj.sketch_file:
            return f"/api/commissions/{obj.id}/download-sketch/"
        return None

    def get_has_final_delivery(self, obj):
        return bool(obj.final_delivery_file)

    def get_delivery_download_url(self, obj):
        if obj.final_delivery_file:
            return f"/api/commissions/{obj.id}/download-deliverable/"
        return None

    def get_certificate_url(self, obj):
        if obj.status == Commission.Status.COMPLETED and obj.is_paid:
            return f"/api/commissions/{obj.id}/certificate/"
        return None

    def get_user_role_in_commission(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return 'GUEST'
        if request.user.id == obj.buyer_id:
            return 'BUYER'
        if request.user.id == obj.creator_id:
            return 'CREATOR'
        if request.user.is_staff:
            return 'STAFF'
        return 'OTHER'

    def get_allowed_actions(self, obj):
        role = self.get_user_role_in_commission(obj)
        actions = []
        if role == 'BUYER':
            if obj.status in [Commission.Status.REQUESTED, Commission.Status.QUOTED] and not obj.is_paid:
                actions.append('CANCEL')
            if obj.status == Commission.Status.QUOTED and obj.active_proposal:
                actions.append('ACCEPT_QUOTE')
                actions.append('DECLINE_QUOTE')
            if obj.status == Commission.Status.DELIVERED:
                actions.append('APPROVE_COMPLETE')
                if obj.revisions_used < obj.agreed_max_revisions:
                    actions.append('REQUEST_REVISION')
        elif role == 'CREATOR':
            if obj.status in [Commission.Status.REQUESTED, Commission.Status.QUOTED]:
                actions.append('SUBMIT_QUOTE')
                actions.append('REJECT')
            if obj.status in [Commission.Status.IN_PROGRESS, Commission.Status.REVISION_REQUESTED]:
                actions.append('UPLOAD_SKETCH')
                actions.append('DELIVER')
        return actions


class CommissionCreateSerializer(serializers.ModelSerializer):
    creator_username = serializers.CharField(write_only=True)
    reference_file = serializers.FileField(required=False, write_only=True)

    class Meta:
        model = Commission
        fields = [
            'id',
            'creator_username',
            'title',
            'description',
            'license_type',
            'budget',
            'deadline',
            'reference_file',
            'commission_code',
        ]
        read_only_fields = ['id', 'commission_code']

    def validate_budget(self, value):
        if value <= Decimal('0'):
            raise serializers.ValidationError('Ngân sách dự kiến phải lớn hơn 0 VND.')
        return value

    def validate_deadline(self, value):
        today = timezone.now().date()
        if value <= today:
            raise serializers.ValidationError('Hạn mong muốn hoàn thành phải là một ngày trong tương lai.')
        return value

    def validate_creator_username(self, value):
        try:
            creator = User.objects.select_related('artist_profile').get(username=value)
        except User.DoesNotExist:
            raise serializers.ValidationError('Không tìm thấy nghệ sĩ này trên hệ thống.')

        if creator.role != User.Role.CREATOR:
            raise serializers.ValidationError('Tài khoản được chọn không có vai trò Nghệ sĩ (Creator).')

        profile = getattr(creator, 'artist_profile', None)
        if not profile or not profile.is_accepting_commissions:
            raise serializers.ValidationError('Nghệ sĩ hiện đang tạm ngừng nhận yêu cầu đặt vẽ (Commission).')

        return creator

    def validate_reference_file(self, value):
        if value:
            # Check size: max 10MB
            validate_file_size(value, max_mb=10, label='tệp tham khảo')
            # Check extension
            allowed_ref = RASTER_EXTENSIONS.union({'.pdf', '.zip'})
            validate_file_extension(value.name, allowed_ref)
        return value

    def validate(self, attrs):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError('Bạn cần đăng nhập để gửi yêu cầu đặt vẽ.')

        creator = attrs.get('creator_username')
        if request.user.id == creator.id:
            raise serializers.ValidationError('Bạn không thể tự gửi yêu cầu đặt vẽ cho chính mình.')

        # Anti-spam / duplicate check
        recent_duplicate = Commission.objects.filter(
            buyer=request.user,
            creator=creator,
            title=attrs.get('title'),
            created_at__gte=timezone.now() - timezone.timedelta(seconds=15)
        ).exists()
        if recent_duplicate:
            raise serializers.ValidationError('Yêu cầu tương tự vừa được gửi. Vui lòng chờ ít giây trước khi thử lại.')

        return attrs

    def create(self, validated_data):
        creator = validated_data.pop('creator_username')
        ref_file = validated_data.pop('reference_file', None)
        buyer = self.context['request'].user

        commission = Commission(
            buyer=buyer,
            creator=creator,
            **validated_data
        )

        if ref_file:
            commission.reference_image = ref_file
            commission.reference_filename = ref_file.name
            commission.reference_size_bytes = ref_file.size

        commission.save()

        # Log initial event
        CommissionEvent.objects.create(
            commission=commission,
            actor=buyer,
            event_type=CommissionEvent.EventType.REQUEST_CREATED,
            title='Người mua gửi yêu cầu đặt vẽ mới',
            note=f"Ngân sách dự kiến: {int(commission.budget):,} VND • Hạn hoàn thành: {commission.deadline.strftime('%d/%m/%Y')} • Gói quyền: {commission.get_license_type_display()}"
        )

        return commission
