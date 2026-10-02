from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token, rotate_token
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator
from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import RetrieveAPIView, RetrieveUpdateAPIView

from .models import User, ArtistProfile
from .serializers import (
    RegisterSerializer,
    LoginSerializer,
    UserMeSerializer,
    ArtistProfileSerializer,
    PublicArtistProfileSerializer,
)
from .permissions import IsCreator


@method_decorator(ensure_csrf_cookie, name='dispatch')
class CSRFTokenView(APIView):
    """
    Endpoint to obtain CSRF cookie and token for session-based API requests.
    Guarantees the csrftoken cookie is sent in Set-Cookie header.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        token = get_token(request)
        return Response({
            'detail': 'CSRF cookie set successfully.',
            'csrf_token': token
        })


@method_decorator(ensure_csrf_cookie, name='dispatch')
class RegisterView(APIView):
    """
    Public user registration.
    Supports role selection (BUYER or CREATOR).
    Cannot grant admin or verified privileges.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            data = UserMeSerializer(user).data
            data['csrf_token'] = get_token(request)
            return Response(
                data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(ensure_csrf_cookie, name='dispatch')
class LoginView(APIView):
    """
    Session login endpoint.
    Verifies credentials and initiates a Django session with CSRF protection.
    Rotates CSRF token and immediately returns the new valid token in payload.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        username = serializer.validated_data['username']
        password = serializer.validated_data['password']

        user = authenticate(request, username=username, password=password)
        if user is None:
            return Response(
                {'detail': 'Tên đăng nhập hoặc mật khẩu không chính xác.'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        if not user.is_active:
            return Response(
                {'detail': 'Tài khoản đã bị vô hiệu hóa.'},
                status=status.HTTP_403_FORBIDDEN
            )

        login(request, user)
        # login() rotates token; get_token(request) retrieves the active rotated token
        active_csrf = get_token(request)
        return Response({
            'detail': 'Đăng nhập thành công.',
            'csrf_token': active_csrf,
            'user': UserMeSerializer(user).data
        }, status=status.HTTP_200_OK)


@method_decorator(ensure_csrf_cookie, name='dispatch')
class LogoutView(APIView):
    """
    Session logout endpoint.
    Clears the Django session and refreshes CSRF token for subsequent guest requests.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        if request.user.is_authenticated:
            logout(request)
        new_csrf = get_token(request)
        return Response(
            {
                'detail': 'Đăng xuất thành công.',
                'csrf_token': new_csrf
            },
            status=status.HTTP_200_OK
        )


class UserMeView(RetrieveUpdateAPIView):
    """
    View and update profile of currently authenticated user.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserMeSerializer

    def get_object(self):
        return self.request.user


class ArtistProfileView(RetrieveUpdateAPIView):
    """
    Creator-only view to inspect and update their own artist profile.
    """
    permission_classes = [permissions.IsAuthenticated, IsCreator]
    serializer_class = ArtistProfileSerializer

    def get_object(self):
        profile, _ = ArtistProfile.objects.get_or_create(
            user=self.request.user,
            defaults={'display_name': self.request.user.username}
        )
        return profile


class PublicArtistProfileView(RetrieveAPIView):
    """
    Public view for artist profile by username.
    Hides private contact details and unverified credentials.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = PublicArtistProfileSerializer
    lookup_field = 'user__username'
    lookup_url_kwarg = 'username'

    def get_queryset(self):
        return ArtistProfile.objects.filter(user__role=User.Role.CREATOR, user__is_active=True)


class NotificationListView(APIView):
    """
    List latest notifications for current user and unread count.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        notifications = Notification.objects.filter(recipient=user).order_by('-created_at')
        unread_count = notifications.filter(is_read=False).count()
        data = NotificationSerializer(notifications[:30], many=True).data
        return Response({
            'unread_count': unread_count,
            'notifications': data
        })


class NotificationMarkReadView(APIView):
    """
    Mark single notification as read.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
        notification.is_read = True
        notification.save(update_fields=['is_read'])
        return Response({
            'detail': 'Đã đánh dấu thông báo là đã đọc.',
            'id': notification.id
        })


class NotificationMarkAllReadView(APIView):
    """
    Mark all unread notifications for current user as read.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        updated_count = Notification.objects.filter(
            recipient=request.user,
            is_read=False
        ).update(is_read=True)
        return Response({
            'detail': 'Đã đánh dấu tất cả thông báo là đã đọc.',
            'updated_count': updated_count
        })


class ArtistReviewsByUsernameView(APIView):
    """
    Public view: list verified buyer reviews for an artist.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, username):
        artist = get_object_or_404(User, username=username, role=User.Role.CREATOR, is_active=True)
        profile = getattr(artist, 'artist_profile', None)
        reviews = ArtistReview.objects.filter(artist=artist).select_related('reviewer').order_by('-created_at')
        return Response({
            'artist_username': artist.username,
            'average_rating': profile.average_rating if profile else None,
            'review_count': profile.review_count if profile else 0,
            'activity_tier': profile.activity_tier if profile else None,
            'reviews': ArtistReviewSerializer(reviews, many=True).data
        })


class ArtistReviewCreateUpdateView(APIView):
    """
    Write or update review for an artist.
    Strictly verifies that:
    1. Reviewer is authenticated and reviewer != artist.
    2. Reviewer has a COMPLETED Order or COMPLETED Commission with this artist.
    3. Exactly 1 review per transaction; only author can edit.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from artworks.models import Order
        from commissions.models import Commission

        artist_username = request.data.get('artist_username', '').strip()
        order_code = request.data.get('order_code', '').strip()
        commission_id = request.data.get('commission_id')
        rating = request.data.get('rating')
        comment = (request.data.get('comment') or '').strip()

        if not artist_username:
            return Response({'detail': 'Thiếu tên nghệ sĩ được đánh giá.'}, status=status.HTTP_400_BAD_REQUEST)

        artist = get_object_or_404(User, username=artist_username, role=User.Role.CREATOR)
        if artist.id == request.user.id:
            return Response({'detail': 'Bạn không thể tự đánh giá chính mình.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            rating = int(rating)
            if rating < 1 or rating > 5:
                raise ValueError()
        except (TypeError, ValueError):
            return Response({'detail': 'Điểm đánh giá phải từ 1 đến 5 sao.'}, status=status.HTTP_400_BAD_REQUEST)

        if not comment:
            return Response({'detail': 'Vui lòng nhập nhận xét của bạn.'}, status=status.HTTP_400_BAD_REQUEST)

        order_obj = None
        commission_obj = None

        if order_code:
            order_obj = Order.objects.filter(
                order_code=order_code,
                buyer=request.user,
                artwork__creator=artist,
                status=Order.Status.COMPLETED
            ).first()
            if not order_obj:
                return Response(
                    {'detail': 'Không tìm thấy đơn mua hoàn tất phù hợp giữa bạn và nghệ sĩ này.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        elif commission_id:
            commission_obj = Commission.objects.filter(
                pk=commission_id,
                buyer=request.user,
                creator=artist,
                status=Commission.Status.COMPLETED
            ).first()
            if not commission_obj:
                return Response(
                    {'detail': 'Không tìm thấy đơn đặt vẽ hoàn tất phù hợp giữa bạn và nghệ sĩ này.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            # Auto-detect any completed order or commission between buyer and artist
            order_obj = Order.objects.filter(
                buyer=request.user,
                artwork__creator=artist,
                status=Order.Status.COMPLETED
            ).first()
            if not order_obj:
                commission_obj = Commission.objects.filter(
                    buyer=request.user,
                    creator=artist,
                    status=Commission.Status.COMPLETED
                ).first()

            if not order_obj and not commission_obj:
                return Response(
                    {'detail': 'Chỉ người mua đã có giao dịch hoàn tất thành công với nghệ sĩ mới được gửi đánh giá.'},
                    status=status.HTTP_403_FORBIDDEN
                )

        # Check existing review
        existing_review = None
        if order_obj:
            existing_review = ArtistReview.objects.filter(order=order_obj).first()
        elif commission_obj:
            existing_review = ArtistReview.objects.filter(commission=commission_obj).first()

        if existing_review:
            if existing_review.reviewer_id != request.user.id:
                return Response({'detail': 'Bạn không có quyền chỉnh sửa đánh giá này.'}, status=status.HTTP_403_FORBIDDEN)
            existing_review.rating = rating
            existing_review.comment = comment
            existing_review.save()
            return Response({
                'detail': 'Cập nhật đánh giá thành công.',
                'review': ArtistReviewSerializer(existing_review).data
            })

        review = ArtistReview.objects.create(
            artist=artist,
            reviewer=request.user,
            order=order_obj,
            commission=commission_obj,
            rating=rating,
            comment=comment
        )
        return Response({
            'detail': 'Đăng đánh giá thành công.',
            'review': ArtistReviewSerializer(review).data
        }, status=status.HTTP_201_CREATED)

