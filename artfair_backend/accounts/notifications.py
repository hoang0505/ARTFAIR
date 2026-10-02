from .models import Notification


def create_notification(recipient, title, message, notification_type=Notification.NotificationType.SYSTEM, target_url='', reference_id=''):
    """
    Creates a notification for recipient with idempotency check via reference_id.
    If reference_id is provided and already exists for recipient, does not create a duplicate.
    """
    if not recipient:
        return None

    if reference_id:
        existing = Notification.objects.filter(recipient=recipient, reference_id=reference_id).first()
        if existing:
            return existing

    return Notification.objects.create(
        recipient=recipient,
        title=title,
        message=message,
        notification_type=notification_type,
        target_url=target_url,
        reference_id=reference_id
    )
