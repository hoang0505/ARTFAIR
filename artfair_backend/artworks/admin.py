from django.contrib import admin
from .models import Category, Tag, Artwork, ArtworkFile, LicenseOption, Order, Withdrawal


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'created_at')
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'created_at')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}


class LicenseOptionInline(admin.TabularInline):
    model = LicenseOption
    extra = 2
    fields = ('license_type', 'price', 'is_active', 'terms')


class ArtworkFileInline(admin.StackedInline):
    model = ArtworkFile
    extra = 0
    readonly_fields = ('original_filename', 'file_format', 'file_size_bytes', 'width', 'height', 'dpi', 'color_mode', 'created_at')
    can_delete = True


@admin.register(Artwork)
class ArtworkAdmin(admin.ModelAdmin):
    list_display = ('title', 'creator', 'category', 'status', 'created_at')
    list_filter = ('status', 'category', 'created_at')
    search_fields = ('title', 'creator__username', 'description')
    prepopulated_fields = {'slug': ('title',)}
    filter_horizontal = ('tags',)
    inlines = [ArtworkFileInline, LicenseOptionInline]


@admin.register(ArtworkFile)
class ArtworkFileAdmin(admin.ModelAdmin):
    list_display = ('original_filename', 'artwork', 'file_format', 'file_size_bytes', 'dpi', 'color_mode', 'created_at')
    list_filter = ('file_format', 'color_mode', 'created_at')
    search_fields = ('original_filename', 'artwork__title', 'artwork__creator__username')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(LicenseOption)
class LicenseOptionAdmin(admin.ModelAdmin):
    list_display = ('artwork', 'license_type', 'price', 'is_active', 'updated_at')
    list_filter = ('license_type', 'is_active')
    search_fields = ('artwork__title', 'artwork__creator__username')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_code', 'buyer', 'artwork', 'license_type', 'price_paid', 'status', 'created_at')
    list_filter = ('status', 'license_type', 'created_at')
    search_fields = ('order_code', 'buyer__username', 'artwork__title')
    readonly_fields = ('order_code', 'created_at', 'completed_at')



@admin.register(Withdrawal)
class WithdrawalAdmin(admin.ModelAdmin):
    list_display = ('withdrawal_code', 'creator', 'amount', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('withdrawal_code', 'creator__username')
    readonly_fields = ('withdrawal_code', 'created_at')
