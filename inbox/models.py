from django.conf import settings
from django.db import models


class OwnerMessage(models.Model):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="owner_messages_received",
        on_delete=models.CASCADE,
    )
    project = models.ForeignKey(
        "projects.Project",
        related_name="owner_messages",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    sender_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="owner_messages_sent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    sender_name = models.CharField(max_length=120, blank=True)
    sender_email = models.EmailField(blank=True)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["recipient", "created_at"],
                name="owner_msg_rec_created_idx",
            ),
            models.Index(
                fields=["project", "created_at"],
                name="owner_msg_proj_created_idx",
            ),
        ]

    def __str__(self):
        return f"Message to @{self.recipient.handle}"
