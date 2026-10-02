from rest_framework import permissions


class IsCreator(permissions.BasePermission):
    """
    Permission check: only authenticated creators have permission.
    """
    message = "Chỉ tài khoản Creator (Nghệ sĩ) mới có quyền thực hiện thao tác này."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_creator)


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Object-level permission to only allow owners of an object to edit it.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True

        # Check if obj has creator attribute (Artwork) or user attribute (ArtistProfile)
        owner = getattr(obj, 'creator', getattr(obj, 'user', None))
        return owner == request.user
