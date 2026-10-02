from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import User, ArtistProfile


@receiver(post_save, sender=User)
def handle_user_creator_profile(sender, instance, created, **kwargs):
    """
    Ensure ArtistProfile is automatically created when a user is a CREATOR.
    Buyers do not get an ArtistProfile.
    """
    if instance.role == User.Role.CREATOR:
        ArtistProfile.objects.get_or_create(
            user=instance,
            defaults={
                'display_name': instance.username,
                'bio': '',
                'is_accepting_commissions': False,
            }
        )
