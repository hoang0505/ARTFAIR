from rest_framework import serializers
from .models import User, ArtistProfile, Notification, ArtistReview


class RegisterSerializer(serializers.ModelSerializer):
    """
    Public registration serializer.
    Prevents assigning admin, staff, or verification status.
    Password is securely hashed.
    """
    password = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8,
        style={'input_type': 'password'}
    )
    role = serializers.ChoiceField(
        choices=User.Role.choices,
        default=User.Role.BUYER
    )

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'password', 'role')

    def validate_email(self, value):
        normalized = User.objects.normalize_email(value)
        if User.objects.filter(email__iexact=normalized).exists():
            raise serializers.ValidationError("Địa chỉ email này đã được sử dụng.")
        return normalized

    def create(self, validated_data):
        # Create user through CustomUserManager, ensuring password hashing
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            role=validated_data.get('role', User.Role.BUYER),
            is_staff=False,
            is_superuser=False,
            is_email_verified=False
        )
        return user


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(required=True)
    password = serializers.CharField(required=True, write_only=True, style={'input_type': 'password'})


class ArtistProfileSerializer(serializers.ModelSerializer):
    """
    Artist Profile serializer for owner viewing & editing.
    """
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = ArtistProfile
        fields = (
            'id',
            'username',
            'display_name',
            'bio',
            'avatar',
            'cover_image',
            'is_accepting_commissions',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')


class PublicArtistProfileSerializer(serializers.ModelSerializer):
    """
    Public profile of an artist.
    No private emails or sensitive attributes.
    """
    username = serializers.CharField(source='user.username', read_only=True)
    published_artworks_count = serializers.SerializerMethodField()

    average_rating = serializers.ReadOnlyField()
    review_count = serializers.ReadOnlyField()
    activity_tier = serializers.ReadOnlyField()

    class Meta:
        model = ArtistProfile
        fields = (
            'username',
            'display_name',
            'bio',
            'avatar',
            'cover_image',
            'is_accepting_commissions',
            'published_artworks_count',
            'average_rating',
            'review_count',
            'activity_tier',
            'created_at',
        )

    def get_published_artworks_count(self, obj):
        return obj.user.artworks.filter(status='PUBLISHED').count()


class UserMeSerializer(serializers.ModelSerializer):
    """
    Serializer for the current authenticated user's own profile.
    """
    artist_profile = ArtistProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = (
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'role',
            'is_email_verified',
            'date_joined',
            'artist_profile',
        )
        read_only_fields = ('id', 'username', 'role', 'is_email_verified', 'date_joined')

    def validate_email(self, value):
        normalized = User.objects.normalize_email(value)
        current_id = self.instance.pk if self.instance else None
        if User.objects.filter(email__iexact=normalized).exclude(pk=current_id).exists():
            raise serializers.ValidationError("Địa chỉ email này đã được sử dụng.")
        return normalized


class NotificationSerializer(serializers.ModelSerializer):
    created_at_formatted = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = (
            'id',
            'title',
            'message',
            'notification_type',
            'target_url',
            'is_read',
            'created_at',
            'created_at_formatted',
        )

    def get_created_at_formatted(self, obj):
        return obj.created_at.strftime('%d/%m/%Y %H:%M')


class ArtistReviewSerializer(serializers.ModelSerializer):
    reviewer_username = serializers.CharField(source='reviewer.username', read_only=True)
    created_at_formatted = serializers.SerializerMethodField()

    class Meta:
        model = ArtistReview
        fields = (
            'id',
            'reviewer_username',
            'rating',
            'comment',
            'created_at',
            'created_at_formatted',
        )
        read_only_fields = ('id', 'reviewer_username', 'created_at', 'created_at_formatted')

    def get_created_at_formatted(self, obj):
        return obj.created_at.strftime('%d/%m/%Y')

