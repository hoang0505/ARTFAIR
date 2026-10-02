import os
import json
from decimal import Decimal
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, FileResponse, Http404, JsonResponse
from django.core.paginator import Paginator
from django.contrib.auth import get_user_model

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Commission, CommissionProposal, CommissionEvent
from .serializers import (
    CommissionDetailSerializer,
    CommissionCreateSerializer,
    CommissionProposalSerializer,
    CommissionEventSerializer
)
from artworks.models import Artwork
from artworks.utils import (
    validate_file_size,
    validate_file_extension,
    generate_commission_certificate_pdf,
    ALLOWED_ORIGINAL_EXTENSIONS,
    RASTER_EXTENSIONS
)

User = get_user_model()


class CommissionViewSet(viewsets.ModelViewSet):
    """
    DRF ViewSet for managing Commissions.
    Strictly isolated: users can only see commissions where they are buyer or creator.
    """
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Commission.objects.none()

        qs = Commission.objects.select_related(
            'buyer',
            'creator',
            'creator__artist_profile'
        ).prefetch_related(
            'proposals',
            'events'
        )

        role = self.request.query_params.get('role')
        if role == 'buyer':
            qs = qs.filter(buyer=user)
        elif role == 'creator':
            qs = qs.filter(creator=user)
        elif not user.is_staff:
            qs = qs.filter(Q(buyer=user) | Q(creator=user))

        return qs.order_by('-created_at')

    def get_serializer_class(self):
        if self.action == 'create':
            return CommissionCreateSerializer
        return CommissionDetailSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Strictly verify access
        if instance.buyer_id != request.user.id and instance.creator_id != request.user.id and not request.user.is_staff:
            return Response({'detail': 'Bạn không có quyền truy cập yêu cầu đặt vẽ này.'}, status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        commission = serializer.save()

        try:
            from accounts.notifications import create_notification
            create_notification(
                recipient=commission.creator,
                title="Yêu cầu Commission mới",
                message=f"Người mua @{commission.buyer.username} đã gửi yêu cầu đặt vẽ mới: '{commission.title}' (Ngân sách: {int(commission.budget):,}₫).",
                notification_type='COMMISSION_REQUESTED',
                target_url=f"/commissions/{commission.id}/",
                reference_id=f"comm_req_{commission.id}"
            )
        except Exception:
            pass

        detail_serializer = CommissionDetailSerializer(commission, context={'request': request})
        return Response(detail_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='submit-proposal')
    def submit_proposal(self, request, pk=None):
        """
        Creator submits an official quote/proposal.
        """
        commission = self.get_object()
        if commission.creator_id != request.user.id and not request.user.is_staff:
            return Response({'detail': 'Chỉ nghệ sĩ được yêu cầu mới có quyền gửi báo giá.'}, status=status.HTTP_403_FORBIDDEN)

        if commission.status not in [Commission.Status.REQUESTED, Commission.Status.QUOTED]:
            return Response({'detail': f'Không thể gửi báo giá ở trạng thái hiện tại ({commission.get_status_display()}).'}, status=status.HTTP_400_BAD_REQUEST)

        price = request.data.get('price')
        delivery_date = request.data.get('delivery_date')
        scope_of_work = (request.data.get('scope_of_work') or '').strip()
        max_revisions = request.data.get('max_revisions', 1)
        license_terms = (request.data.get('license_terms') or '').strip()
        sketch_file = request.FILES.get('sketch_file')

        if not price or not delivery_date or not scope_of_work:
            return Response({'detail': 'Vui lòng điền đầy đủ giá báo, ngày dự kiến bàn giao và phạm vi công việc.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            price = Decimal(str(price))
            if price <= Decimal('0'):
                raise ValueError()
        except Exception:
            return Response({'detail': 'Giá báo giá phải là số tiền hợp lệ (> 0 VND).'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from datetime import datetime
            deliv_date_obj = datetime.strptime(str(delivery_date).strip(), '%Y-%m-%d').date()
            if deliv_date_obj < timezone.now().date():
                return Response({'detail': 'Hạn bàn giao phải ở tương lai.'}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError:
            return Response({'detail': 'Định dạng ngày bàn giao không hợp lệ (YYYY-MM-DD).'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            max_revisions = int(max_revisions)
            if max_revisions < 0:
                max_revisions = 0
        except (ValueError, TypeError):
            max_revisions = 1

        if sketch_file:
            try:
                validate_file_size(sketch_file, max_mb=10, label='tệp phác thảo')
                validate_file_extension(sketch_file.name, RASTER_EXTENSIONS.union({'.pdf', '.zip'}))
            except Exception as e:
                return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            # Mark existing active proposal as superseded
            current_active = commission.active_proposal
            next_version = 1
            if current_active:
                current_active.status = CommissionProposal.Status.SUPERSEDED
                current_active.save(update_fields=['status'])
                next_version = current_active.version + 1
            else:
                highest_prop = commission.proposals.order_by('-version').first()
                if highest_prop:
                    next_version = highest_prop.version + 1

            proposal = CommissionProposal.objects.create(
                commission=commission,
                creator=request.user,
                version=next_version,
                price=price,
                delivery_date=deliv_date_obj,
                scope_of_work=scope_of_work,
                max_revisions=max_revisions,
                license_terms=license_terms,
                sketch_file=sketch_file,
                status=CommissionProposal.Status.PENDING
            )

            commission.status = Commission.Status.QUOTED
            commission.save(update_fields=['status', 'updated_at'])

            CommissionEvent.objects.create(
                commission=commission,
                actor=request.user,
                event_type=CommissionEvent.EventType.PROPOSAL_SENT,
                title=f'Nghệ sĩ gửi báo giá phiên bản {next_version}',
                note=f"Giá: {int(price):,} VND • Hạn bàn giao: {deliv_date_obj.strftime('%d/%m/%Y')} • {max_revisions} lần sửa"
            )

            try:
                from accounts.notifications import create_notification
                create_notification(
                    recipient=commission.buyer,
                    title="Nghệ sĩ gửi báo giá mới",
                    message=f"Nghệ sĩ @{commission.creator.username} đã gửi báo giá ({int(price):,}₫) cho yêu cầu #{commission.id}.",
                    notification_type='COMMISSION_PROPOSAL',
                    target_url=f"/commissions/{commission.id}/",
                    reference_id=f"comm_prop_{proposal.id}"
                )
            except Exception:
                pass

        serializer = CommissionDetailSerializer(commission, context={'request': request})
        return Response({
            'detail': 'Đã gửi báo giá thành công tới Người mua.',
            'commission': serializer.data
        })

    @action(detail=True, methods=['post'], url_path='decline-proposal')
    def decline_proposal(self, request, pk=None):
        """
        Buyer declines the creator's current proposal.
        """
        commission = self.get_object()
        if commission.buyer_id != request.user.id and not request.user.is_staff:
            return Response({'detail': 'Chỉ người mua mới có quyền từ chối báo giá.'}, status=status.HTTP_403_FORBIDDEN)

        if commission.status != Commission.Status.QUOTED:
            return Response({'detail': 'Hiện không có báo giá chờ duyệt.'}, status=status.HTTP_400_BAD_REQUEST)

        active_prop = commission.active_proposal
        if not active_prop:
            return Response({'detail': 'Không tìm thấy báo giá đang chờ duyệt.'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            active_prop.status = CommissionProposal.Status.REJECTED
            active_prop.save(update_fields=['status'])

            CommissionEvent.objects.create(
                commission=commission,
                actor=request.user,
                event_type=CommissionEvent.EventType.PROPOSAL_REJECTED,
                title=f'Người mua từ chối báo giá phiên bản {active_prop.version}',
                note='Người mua mong muốn nghệ sĩ điều chỉnh lại báo giá hoặc thương lượng thêm.'
            )

        serializer = CommissionDetailSerializer(commission, context={'request': request})
        return Response({
            'detail': 'Đã từ chối báo giá. Nghệ sĩ có thể gửi lại báo giá điều chỉnh.',
            'commission': serializer.data
        })

    @action(detail=True, methods=['post'], url_path='accept-and-pay')
    def accept_and_pay(self, request, pk=None):
        """
        Buyer accepts the active proposal and simulates escrow payment.
        """
        commission = self.get_object()
        if commission.buyer_id != request.user.id and not request.user.is_staff:
            return Response({'detail': 'Chỉ người mua mới có quyền chấp nhận và thanh toán.'}, status=status.HTTP_403_FORBIDDEN)

        if commission.status != Commission.Status.QUOTED:
            return Response({'detail': 'Đơn hàng không ở trạng thái chờ duyệt báo giá.'}, status=status.HTTP_400_BAD_REQUEST)

        sim_action = request.data.get('action', 'SUCCESS')
        if sim_action == 'CANCEL':
            return Response({'detail': 'Đã hủy thao tác thanh toán mô phỏng.'})

        if sim_action != 'SUCCESS':
            return Response({'detail': 'Giao dịch mô phỏng không thành công.'}, status=status.HTTP_400_BAD_REQUEST)

        active_prop = commission.active_proposal
        if not active_prop:
            return Response({'detail': 'Không tìm thấy báo giá hợp lệ để chấp nhận.'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            # Snapshot agreed terms
            commission.agreed_price = active_prop.price
            commission.agreed_delivery_date = active_prop.delivery_date
            commission.agreed_scope = active_prop.scope_of_work
            commission.agreed_terms = active_prop.license_terms
            commission.agreed_max_revisions = active_prop.max_revisions
            commission.revisions_used = 0
            commission.is_paid = True
            commission.paid_at = timezone.now()
            commission.status = Commission.Status.IN_PROGRESS
            commission.save()

            active_prop.status = CommissionProposal.Status.ACCEPTED
            active_prop.save(update_fields=['status'])

            CommissionEvent.objects.create(
                commission=commission,
                actor=request.user,
                event_type=CommissionEvent.EventType.PAYMENT_COMPLETED,
                title='Người mua chấp nhận báo giá & Hoàn tất thanh toán mô phỏng (Ký quỹ)',
                note=f"Số tiền ký quỹ: {int(commission.agreed_price):,} VND • Hạn bàn giao chốt: {commission.agreed_delivery_date.strftime('%d/%m/%Y')}"
            )

            try:
                from accounts.notifications import create_notification
                create_notification(
                    recipient=commission.creator,
                    title="Người mua đã ký quỹ (Escrow)",
                    message=f"Người mua @{commission.buyer.username} đã thanh toán ký quỹ ({int(commission.agreed_price):,}₫) cho yêu cầu #{commission.id}. Hãy bắt đầu sáng tác!",
                    notification_type='COMMISSION_PAID',
                    target_url=f"/commissions/{commission.id}/",
                    reference_id=f"comm_paid_{commission.id}"
                )
            except Exception:
                pass

        serializer = CommissionDetailSerializer(commission, context={'request': request})
        return Response({
            'detail': 'Thanh toán mô phỏng thành công! Đơn đặt vẽ đã chuyển sang trạng thái Đang thực hiện.',
            'commission': serializer.data
        })

    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel_commission(self, request, pk=None):
        """
        Buyer cancels request before payment.
        """
        commission = self.get_object()
        if commission.buyer_id != request.user.id and not request.user.is_staff:
            return Response({'detail': 'Chỉ người mua mới có quyền hủy đơn.'}, status=status.HTTP_403_FORBIDDEN)

        if commission.is_paid:
            return Response({'detail': 'Đơn hàng đã thanh toán ký quỹ không thể tự ý hủy. Vui lòng liên hệ hỗ trợ.'}, status=status.HTTP_400_BAD_REQUEST)

        if commission.status not in [Commission.Status.REQUESTED, Commission.Status.QUOTED]:
            return Response({'detail': f'Không thể hủy đơn ở trạng thái {commission.get_status_display()}.'}, status=status.HTTP_400_BAD_REQUEST)

        reason = (request.data.get('cancellation_reason') or '').strip()

        with transaction.atomic():
            commission.status = Commission.Status.CANCELLED
            commission.cancellation_reason = reason
            commission.save(update_fields=['status', 'cancellation_reason', 'updated_at'])

            CommissionEvent.objects.create(
                commission=commission,
                actor=request.user,
                event_type=CommissionEvent.EventType.CANCELLED,
                title='Người mua đã hủy yêu cầu đặt vẽ',
                note=reason or 'Người mua chủ động hủy trước khi thanh toán ký quỹ.'
            )

        serializer = CommissionDetailSerializer(commission, context={'request': request})
        return Response({
            'detail': 'Đã hủy yêu cầu đặt vẽ thành công.',
            'commission': serializer.data
        })

    @action(detail=True, methods=['post'], url_path='reject')
    def reject_commission(self, request, pk=None):
        """
        Creator rejects request before starting work.
        """
        commission = self.get_object()
        if commission.creator_id != request.user.id and not request.user.is_staff:
            return Response({'detail': 'Chỉ nghệ sĩ được yêu cầu mới có quyền từ chối.'}, status=status.HTTP_403_FORBIDDEN)

        if commission.status not in [Commission.Status.REQUESTED, Commission.Status.QUOTED]:
            return Response({'detail': f'Không thể từ chối ở trạng thái {commission.get_status_display()}.'}, status=status.HTTP_400_BAD_REQUEST)

        reason = (request.data.get('rejection_reason') or '').strip()
        if not reason:
            return Response({'detail': 'Vui lòng cung cấp lý do từ chối để thông báo cho người mua.'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            commission.status = Commission.Status.REJECTED
            commission.rejection_reason = reason
            commission.save(update_fields=['status', 'rejection_reason', 'updated_at'])

            CommissionEvent.objects.create(
                commission=commission,
                actor=request.user,
                event_type=CommissionEvent.EventType.REJECTED,
                title='Nghệ sĩ từ chối yêu cầu đặt vẽ',
                note=f"Lý do: {reason}"
            )

        serializer = CommissionDetailSerializer(commission, context={'request': request})
        return Response({
            'detail': 'Đã từ chối yêu cầu đặt vẽ thành công.',
            'commission': serializer.data
        })

    @action(detail=True, methods=['post'], url_path='upload-sketch')
    def upload_sketch(self, request, pk=None):
        """
        Creator uploads progress sketches for client review.
        """
        commission = self.get_object()
        if commission.creator_id != request.user.id and not request.user.is_staff:
            return Response({'detail': 'Chỉ nghệ sĩ mới có quyền tải lên phác thảo tiến độ.'}, status=status.HTTP_403_FORBIDDEN)

        if commission.status not in [Commission.Status.IN_PROGRESS, Commission.Status.REVISION_REQUESTED]:
            return Response({'detail': 'Đơn hàng chưa ở trạng thái đang thực hiện.'}, status=status.HTTP_400_BAD_REQUEST)

        sketch_file = request.FILES.get('sketch_file')
        if not sketch_file:
            return Response({'detail': 'Vui lòng chọn tệp phác thảo để tải lên.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_file_size(sketch_file, max_mb=15, label='tệp phác thảo')
            validate_file_extension(sketch_file.name, RASTER_EXTENSIONS.union({'.pdf', '.zip'}))
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            commission.sketch_file = sketch_file
            commission.sketch_filename = sketch_file.name
            commission.save(update_fields=['sketch_file', 'sketch_filename', 'updated_at'])

            CommissionEvent.objects.create(
                commission=commission,
                actor=request.user,
                event_type=CommissionEvent.EventType.SKETCH_UPLOADED,
                title='Nghệ sĩ tải lên phác thảo tiến độ mới',
                note=f"Tệp: {sketch_file.name}"
            )

        serializer = CommissionDetailSerializer(commission, context={'request': request})
        return Response({
            'detail': 'Đã tải lên phác thảo tiến độ thành công.',
            'commission': serializer.data
        })

    @action(detail=True, methods=['post'], url_path='deliver')
    def deliver_artwork(self, request, pk=None):
        """
        Creator delivers the final artwork file into protected storage.
        """
        commission = self.get_object()
        if commission.creator_id != request.user.id and not request.user.is_staff:
            return Response({'detail': 'Chỉ nghệ sĩ mới có quyền bàn giao tác phẩm.'}, status=status.HTTP_403_FORBIDDEN)

        if commission.status not in [Commission.Status.IN_PROGRESS, Commission.Status.REVISION_REQUESTED]:
            return Response({'detail': f'Không thể bàn giao ở trạng thái {commission.get_status_display()}.'}, status=status.HTTP_400_BAD_REQUEST)

        delivery_file = request.FILES.get('final_delivery_file') or request.FILES.get('delivery_file')
        delivery_note = (request.data.get('final_delivery_note') or request.data.get('delivery_note') or '').strip()

        if not delivery_file:
            return Response({'detail': 'Vui lòng đính kèm tệp bàn giao hoàn chỉnh.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_file_size(delivery_file, max_mb=50, label='tệp bàn giao hoàn chỉnh')
            validate_file_extension(delivery_file.name, ALLOWED_ORIGINAL_EXTENSIONS)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            commission.final_delivery_file = delivery_file
            commission.final_delivery_filename = delivery_file.name
            commission.final_delivery_size_bytes = delivery_file.size
            commission.final_delivery_note = delivery_note
            commission.status = Commission.Status.DELIVERED
            commission.save()

            CommissionEvent.objects.create(
                commission=commission,
                actor=request.user,
                event_type=CommissionEvent.EventType.DELIVERED,
                title='Nghệ sĩ đã bàn giao tác phẩm hoàn chỉnh',
                note=delivery_note or f"Tệp bàn giao: {delivery_file.name}"
            )

            try:
                from accounts.notifications import create_notification
                create_notification(
                    recipient=commission.buyer,
                    title="Nghệ sĩ đã bàn giao tác phẩm",
                    message=f"Nghệ sĩ @{commission.creator.username} đã bàn giao tác phẩm hoàn chỉnh cho yêu cầu #{commission.id}. Vui lòng kiểm tra và nghiệm thu.",
                    notification_type='COMMISSION_DELIVERED',
                    target_url=f"/commissions/{commission.id}/",
                    reference_id=f"comm_deliv_{commission.id}_{commission.revisions_used}"
                )
            except Exception:
                pass

        serializer = CommissionDetailSerializer(commission, context={'request': request})
        return Response({
            'detail': 'Bàn giao tác phẩm thành công! Đang chờ Người mua nghiệm thu.',
            'commission': serializer.data
        })

    @action(detail=True, methods=['post'], url_path='request-revision')
    def request_revision(self, request, pk=None):
        """
        Buyer requests a revision within agreed revision limit.
        """
        commission = self.get_object()
        if commission.buyer_id != request.user.id and not request.user.is_staff:
            return Response({'detail': 'Chỉ người mua mới có quyền yêu cầu chỉnh sửa.'}, status=status.HTTP_403_FORBIDDEN)

        if commission.status != Commission.Status.DELIVERED:
            return Response({'detail': 'Chỉ có thể yêu cầu chỉnh sửa sau khi nghệ sĩ đã bàn giao sản phẩm.'}, status=status.HTTP_400_BAD_REQUEST)

        if commission.revisions_used >= commission.agreed_max_revisions:
            return Response({'detail': f'Bạn đã sử dụng hết số lần chỉnh sửa cho phép ({commission.agreed_max_revisions} lần).'}, status=status.HTTP_400_BAD_REQUEST)

        revision_note = (request.data.get('revision_note') or '').strip()
        if not revision_note:
            return Response({'detail': 'Vui lòng nhập nội dung chi tiết cần chỉnh sửa.'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            commission.revisions_used += 1
            commission.status = Commission.Status.REVISION_REQUESTED
            commission.save(update_fields=['revisions_used', 'status', 'updated_at'])

            CommissionEvent.objects.create(
                commission=commission,
                actor=request.user,
                event_type=CommissionEvent.EventType.REVISION_REQUESTED,
                title=f'Người mua yêu cầu chỉnh sửa (Lần {commission.revisions_used}/{commission.agreed_max_revisions})',
                note=revision_note
            )

            try:
                from accounts.notifications import create_notification
                create_notification(
                    recipient=commission.creator,
                    title="Yêu cầu chỉnh sửa Commission",
                    message=f"Người mua @{commission.buyer.username} đã gửi yêu cầu chỉnh sửa (Lần {commission.revisions_used}/{commission.agreed_max_revisions}) cho yêu cầu #{commission.id}.",
                    notification_type='COMMISSION_REVISION',
                    target_url=f"/commissions/{commission.id}/",
                    reference_id=f"comm_rev_{commission.id}_{commission.revisions_used}"
                )
            except Exception:
                pass

        serializer = CommissionDetailSerializer(commission, context={'request': request})
        return Response({
            'detail': 'Đã gửi yêu cầu chỉnh sửa tới nghệ sĩ thành công.',
            'commission': serializer.data
        })

    @action(detail=True, methods=['post'], url_path='complete')
    def complete_commission(self, request, pk=None):
        """
        Buyer approves and completes the commission.
        Atomically marks completed, releases escrow to Creator, and enables PDF certificate.
        """
        commission = self.get_object()
        if commission.buyer_id != request.user.id and not request.user.is_staff:
            return Response({'detail': 'Chỉ người mua mới có quyền nghiệm thu hoàn tất.'}, status=status.HTTP_403_FORBIDDEN)

        if commission.status != Commission.Status.DELIVERED:
            return Response({'detail': 'Đơn hàng chưa được nghệ sĩ bàn giao sản phẩm.'}, status=status.HTTP_400_BAD_REQUEST)

        if commission.is_escrow_released:
            return Response({'detail': 'Doanh thu cho đơn hàng này đã được giải ngân trước đó.'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            commission.status = Commission.Status.COMPLETED
            commission.is_escrow_released = True
            commission.completed_at = timezone.now()
            commission.save(update_fields=['status', 'is_escrow_released', 'completed_at', 'updated_at'])

            CommissionEvent.objects.create(
                commission=commission,
                actor=request.user,
                event_type=CommissionEvent.EventType.COMPLETED,
                title='Nghiệm thu hoàn tất & Doanh thu đã giải ngân mô phỏng cho nghệ sĩ',
                note=f"Số tiền {int(commission.agreed_price):,} VND đã được cộng vào số dư khả dụng của nghệ sĩ @{commission.creator.username}."
            )

            try:
                from accounts.notifications import create_notification
                create_notification(
                    recipient=commission.creator,
                    title="Commission hoàn tất nghiệm thu!",
                    message=f"Chúc mừng! Commission #{commission.id} đã được nghiệm thu hoàn tất. Số tiền {int(commission.agreed_price):,}₫ đã được giải ngân vào số dư của bạn.",
                    notification_type='COMMISSION_COMPLETED',
                    target_url="/dashboard/#tab-revenue",
                    reference_id=f"comm_done_{commission.id}"
                )
            except Exception:
                pass

        serializer = CommissionDetailSerializer(commission, context={'request': request})
        return Response({
            'detail': 'Chúc mừng! Bạn đã hoàn tất nghiệm thu đơn đặt vẽ. Chứng nhận bản quyền đã sẵn sàng tải về.',
            'commission': serializer.data
        })




# ==============================================================================
# Protected Download Views for Commission Files
# ==============================================================================

def download_reference_view(request, pk):
    """
    Download private reference / moodboard file.
    Only Buyer, Creator, and Staff.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'detail': 'Yêu cầu đăng nhập.'}, status=401)

    commission = get_object_or_404(Commission, pk=pk)
    if commission.buyer_id != request.user.id and commission.creator_id != request.user.id and not request.user.is_staff:
        return JsonResponse({'detail': 'Từ chối quyền truy cập tệp tham khảo.'}, status=403)

    if not commission.reference_image:
        raise Http404('Tệp tham khảo không tồn tại.')

    file_field = commission.reference_image
    filename = commission.reference_filename or os.path.basename(file_field.name)
    response = FileResponse(file_field.open('rb'), as_attachment=True, filename=filename)
    return response


def download_sketch_view(request, pk):
    """
    Download private work-in-progress sketch file.
    Only Buyer, Creator, and Staff.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'detail': 'Yêu cầu đăng nhập.'}, status=401)

    commission = get_object_or_404(Commission, pk=pk)
    if commission.buyer_id != request.user.id and commission.creator_id != request.user.id and not request.user.is_staff:
        return JsonResponse({'detail': 'Từ chối quyền truy cập tệp phác thảo.'}, status=403)

    if not commission.sketch_file:
        raise Http404('Tệp phác thảo không tồn tại.')

    file_field = commission.sketch_file
    filename = commission.sketch_filename or os.path.basename(file_field.name)
    response = FileResponse(file_field.open('rb'), as_attachment=True, filename=filename)
    return response


def download_proposal_sketch_view(request, pk, proposal_id):
    """
    Download private proposal sketch file.
    Only Buyer, Creator, and Staff.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'detail': 'Yêu cầu đăng nhập.'}, status=401)

    commission = get_object_or_404(Commission, pk=pk)
    if commission.buyer_id != request.user.id and commission.creator_id != request.user.id and not request.user.is_staff:
        return JsonResponse({'detail': 'Từ chối quyền truy cập tệp phác thảo báo giá.'}, status=403)

    proposal = get_object_or_404(CommissionProposal, pk=proposal_id, commission=commission)
    if not proposal.sketch_file:
        raise Http404('Tệp phác thảo không tồn tại.')

    file_field = proposal.sketch_file
    filename = f"Proposal_Sketch_v{proposal.version}_{os.path.basename(file_field.name)}"
    response = FileResponse(file_field.open('rb'), as_attachment=True, filename=filename)
    return response


def download_deliverable_view(request, pk):
    """
    Download final deliverable master file.
    Allowed for:
    - Creator and Staff (always)
    - Buyer (ONLY IF is_paid is True and delivery exists)
    Others get HTTP 403 Forbidden.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'detail': 'Yêu cầu đăng nhập.'}, status=401)

    commission = get_object_or_404(Commission, pk=pk)

    # Permission verification
    is_creator = (commission.creator_id == request.user.id)
    is_buyer = (commission.buyer_id == request.user.id)
    is_staff = request.user.is_staff

    if not (is_creator or is_buyer or is_staff):
        return JsonResponse({'detail': 'Từ chối quyền truy cập tệp bàn giao.'}, status=403)

    if is_buyer and not commission.is_paid:
        return JsonResponse({'detail': 'Bạn cần hoàn tất thanh toán mô phỏng trước khi tải tệp bàn giao.'}, status=403)

    if not commission.final_delivery_file:
        raise Http404('Nghệ sĩ chưa tải lên tệp bàn giao hoàn chỉnh.')

    file_field = commission.final_delivery_file
    filename = commission.final_delivery_filename or os.path.basename(file_field.name)
    response = FileResponse(file_field.open('rb'), as_attachment=True, filename=filename)
    return response


def download_commission_certificate_view(request, pk):
    """
    Export Commission License Certificate PDF.
    Only available when Commission is COMPLETED and is_paid is True.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'detail': 'Yêu cầu đăng nhập.'}, status=401)

    commission = get_object_or_404(Commission, pk=pk)
    if commission.buyer_id != request.user.id and commission.creator_id != request.user.id and not request.user.is_staff:
        return JsonResponse({'detail': 'Từ chối quyền truy cập chứng nhận.'}, status=403)

    if commission.status != Commission.Status.COMPLETED or not commission.is_paid:
        return JsonResponse({'detail': 'Chứng nhận bản quyền chỉ được phát hành khi đơn đặt vẽ đã hoàn tất nghiệm thu.'}, status=400)

    try:
        pdf_bytes = generate_commission_certificate_pdf(commission)
    except Exception as e:
        return JsonResponse({'detail': f'Lỗi khi xuất chứng nhận PDF: {str(e)}'}, status=500)

    filename = f"Chung_Nhan_Commission_{commission.commission_code}.pdf"
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


# ==============================================================================
# HTML Page Views
# ==============================================================================

def artist_profile_page_view(request, username):
    """
    Renders Screen 05: Public Artist Profile & Commission Hub.
    URL: /artists/<username>/
    """
    artist = get_object_or_404(
        User.objects.select_related('artist_profile'),
        username=username,
        role=User.Role.CREATOR
    )
    profile = getattr(artist, 'artist_profile', None)

    # Artworks by this artist (PUBLISHED only)
    artworks_qs = Artwork.objects.filter(
        creator=artist,
        status=Artwork.Status.PUBLISHED
    ).select_related('category').prefetch_related('license_options').order_by('-created_at')

    paginator = Paginator(artworks_qs, 8)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Real stats (no fake ratings, no fake sales)
    total_artworks_count = artworks_qs.count()
    completed_commissions_count = Commission.objects.filter(
        creator=artist,
        status=Commission.Status.COMPLETED
    ).count()

    is_owner = request.user.is_authenticated and (request.user.id == artist.id)

    from accounts.models import ArtistReview
    from artworks.models import Order

    reviews = ArtistReview.objects.filter(artist=artist).select_related('reviewer').order_by('-created_at')

    # Check if current user is an eligible buyer to write/edit a review
    can_review = False
    eligible_order = None
    eligible_commission = None
    existing_user_review = None

    if request.user.is_authenticated and not is_owner:
        existing_user_review = ArtistReview.objects.filter(artist=artist, reviewer=request.user).first()
        eligible_order = Order.objects.filter(buyer=request.user, artwork__creator=artist, status=Order.Status.COMPLETED).first()
        if not eligible_order:
            eligible_commission = Commission.objects.filter(buyer=request.user, creator=artist, status=Commission.Status.COMPLETED).first()

        if eligible_order or eligible_commission:
            can_review = True

    context = {
        'artist': artist,
        'profile': profile,
        'page_obj': page_obj,
        'total_artworks_count': total_artworks_count,
        'completed_commissions_count': completed_commissions_count,
        'is_owner': is_owner,
        'reviews': reviews,
        'average_rating': profile.average_rating if profile else None,
        'review_count': profile.review_count if profile else 0,
        'activity_tier': profile.activity_tier if profile else None,
        'can_review': can_review,
        'existing_user_review': existing_user_review,
        'eligible_order': eligible_order,
        'eligible_commission': eligible_commission,
    }
    return render(request, 'artist_profile.html', context)


def commission_detail_page_view(request, pk):
    """
    Renders Screen 05: Commission Tracking Page.
    URL: /commissions/<id>/
    Restricted to Buyer, Creator, and Staff.
    """
    if not request.user.is_authenticated:
        return redirect(f"/?auth=login&next=/commissions/{pk}/")

    commission = get_object_or_404(
        Commission.objects.select_related(
            'buyer',
            'creator',
            'creator__artist_profile'
        ).prefetch_related(
            'proposals',
            'events'
        ),
        pk=pk
    )

    if commission.buyer_id != request.user.id and commission.creator_id != request.user.id and not request.user.is_staff:
        return render(request, 'studio_forbidden.html', {
            'reason': 'commission_forbidden',
            'user': request.user
        }, status=403)

    is_buyer = (commission.buyer_id == request.user.id)
    is_creator = (commission.creator_id == request.user.id)

    serializer = CommissionDetailSerializer(commission, context={'request': request})

    context = {
        'commission': commission,
        'commission_json': json.dumps(serializer.data, default=str),
        'is_buyer': is_buyer,
        'is_creator': is_creator,
        'user_role': 'BUYER' if is_buyer else ('CREATOR' if is_creator else 'STAFF'),
    }
    return render(request, 'commission_detail.html', context)
