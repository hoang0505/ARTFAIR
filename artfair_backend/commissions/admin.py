from django.contrib import admin
from .models import Commission, CommissionProposal, CommissionEvent


class CommissionProposalInline(admin.TabularInline):
    model = CommissionProposal
    extra = 0
    fields = ('version', 'price', 'delivery_date', 'max_revisions', 'status', 'created_at')
    readonly_fields = ('created_at',)


class CommissionEventInline(admin.TabularInline):
    model = CommissionEvent
    extra = 0
    fields = ('actor', 'event_type', 'title', 'note', 'created_at')
    readonly_fields = ('actor', 'event_type', 'title', 'note', 'created_at')


@admin.register(Commission)
class CommissionAdmin(admin.ModelAdmin):
    list_display = (
        'commission_code',
        'title',
        'buyer',
        'creator',
        'status',
        'agreed_price',
        'is_paid',
        'is_escrow_released',
        'created_at'
    )
    list_filter = ('status', 'is_paid', 'is_escrow_released', 'license_type')
    search_fields = ('commission_code', 'title', 'buyer__username', 'creator__username')
    readonly_fields = ('commission_code', 'created_at', 'updated_at')
    inlines = [CommissionProposalInline, CommissionEventInline]


@admin.register(CommissionProposal)
class CommissionProposalAdmin(admin.ModelAdmin):
    list_display = ('commission', 'version', 'price', 'delivery_date', 'max_revisions', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('commission__commission_code', 'scope_of_work')


@admin.register(CommissionEvent)
class CommissionEventAdmin(admin.ModelAdmin):
    list_display = ('commission', 'actor', 'event_type', 'title', 'created_at')
    list_filter = ('event_type',)
    search_fields = ('commission__commission_code', 'actor__username', 'title', 'note')
