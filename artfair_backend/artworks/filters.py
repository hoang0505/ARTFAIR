import django_filters
from django.db.models import Q
from .models import Artwork, LicenseOption


class ArtworkFilter(django_filters.FilterSet):
    """
    Public artwork filter.
    Allows filtering by:
    - category (by slug)
    - artist (by creator username)
    - tag (by tag slug)
    - license_type (PERSONAL or COMMERCIAL)
    - min_price: minimum price for specified license_type (or any active license)
    - max_price: maximum price for specified license_type (or any active license)
    """
    category = django_filters.CharFilter(field_name='category__slug', lookup_expr='exact')
    artist = django_filters.CharFilter(field_name='creator__username', lookup_expr='exact')
    tag = django_filters.CharFilter(field_name='tags__slug', lookup_expr='exact')
    license_type = django_filters.ChoiceFilter(
        choices=LicenseOption.LicenseType.choices,
        method='filter_by_license_type'
    )
    min_price = django_filters.NumberFilter(method='filter_by_price_range')
    max_price = django_filters.NumberFilter(method='filter_by_price_range')
    style = django_filters.CharFilter(field_name='style', lookup_expr='icontains')

    class Meta:
        model = Artwork
        fields = ['category', 'artist', 'tag', 'license_type', 'min_price', 'max_price', 'style']

    def filter_by_license_type(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(license_options__license_type=value, license_options__is_active=True).distinct()

    def filter_by_price_range(self, queryset, name, value):
        # We handle price range together taking license_type into account
        min_price = self.data.get('min_price')
        max_price = self.data.get('max_price')
        license_type = self.data.get('license_type')

        q_filter = Q(license_options__is_active=True)

        if license_type:
            q_filter &= Q(license_options__license_type=license_type)

        if min_price:
            try:
                q_filter &= Q(license_options__price__gte=float(min_price))
            except ValueError:
                pass

        if max_price:
            try:
                q_filter &= Q(license_options__price__lte=float(max_price))
            except ValueError:
                pass

        return queryset.filter(q_filter).distinct()
