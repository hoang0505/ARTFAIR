from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, ArtistProfile


class ArtistProfileInline(admin.StackedInline):
    model = ArtistProfile
    can_delete = False
    verbose_name_plural = 'Hồ sơ nghệ sĩ (Chỉ áp dụng cho Creator)'
    extra = 0


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'role', 'is_email_verified', 'is_staff', 'is_active', 'date_joined')
    list_filter = ('role', 'is_email_verified', 'is_staff', 'is_active')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('-date_joined',)

    fieldsets = BaseUserAdmin.fieldsets + (
        ('Thông tin vai trò ARTFAIR', {
            'fields': ('role', 'is_email_verified')
        }),
    )

    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Thông tin vai trò ARTFAIR', {
            'fields': ('role', 'is_email_verified')
        }),
    )

    inlines = [ArtistProfileInline]


@admin.register(ArtistProfile)
class ArtistProfileAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'user', 'is_accepting_commissions', 'created_at', 'updated_at')
    list_filter = ('is_accepting_commissions', 'created_at')
    search_fields = ('display_name', 'user__username', 'user__email', 'bio')
    readonly_fields = ('created_at', 'updated_at')
