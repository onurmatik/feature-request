from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import (
    OAuthAccessToken,
    OAuthApplication,
    OAuthConsent,
    OAuthGrant,
    OAuthRefreshFamily,
    OAuthRefreshToken,
)


def _revoke_principal_credentials(*, application_id, user_id=None):
    now = timezone.now()
    principal = {"application_id": application_id}
    if user_id is not None:
        principal["user_id"] = user_id
    OAuthGrant.objects.filter(
        **principal,
        consumed_at__isnull=True,
    ).update(consumed_at=now)
    OAuthAccessToken.objects.filter(
        **principal,
        revoked_at__isnull=True,
    ).update(revoked_at=now)
    families = OAuthRefreshFamily.objects.filter(
        **principal,
        revoked_at__isnull=True,
    )
    family_ids = list(families.values_list("pk", flat=True))
    families.update(revoked_at=now)
    OAuthRefreshToken.objects.filter(
        family_id__in=family_ids,
        revoked__isnull=True,
    ).update(revoked=now, access_token=None)


@receiver(post_save, sender=get_user_model())
def revoke_oauth_when_user_deactivated(sender, instance, **kwargs):
    if instance.is_active:
        return
    now = timezone.now()
    OAuthGrant.objects.filter(user=instance, consumed_at__isnull=True).update(consumed_at=now)
    OAuthAccessToken.objects.filter(user=instance, revoked_at__isnull=True).update(revoked_at=now)
    families = OAuthRefreshFamily.objects.filter(
        user=instance, revoked_at__isnull=True
    )
    family_ids = list(families.values_list("pk", flat=True))
    families.update(revoked_at=now)
    OAuthRefreshToken.objects.filter(
        family_id__in=family_ids,
        revoked__isnull=True,
    ).update(revoked=now, access_token=None)


@receiver(post_save, sender=OAuthApplication)
def revoke_oauth_when_application_revoked(sender, instance, **kwargs):
    if instance.revoked_at is None:
        return
    _revoke_principal_credentials(application_id=instance.pk)


@receiver(post_save, sender=OAuthConsent)
def revoke_oauth_when_consent_revoked(sender, instance, **kwargs):
    if instance.revoked_at is None:
        return
    _revoke_principal_credentials(
        application_id=instance.application_id,
        user_id=instance.user_id,
    )
