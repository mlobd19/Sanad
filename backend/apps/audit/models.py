from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    """Journal append-only : chaque action sensible laisse une trace."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    action = models.CharField(max_length=64, db_index=True)
    object_type = models.CharField(max_length=64)
    object_id = models.CharField(max_length=64)
    data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("Un événement d'audit ne se modifie pas.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Un événement d'audit ne se supprime pas.")

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action} {self.object_type}#{self.object_id}"


def record(action, obj, actor=None, **data):
    actor = actor if getattr(actor, "is_authenticated", False) else None
    return AuditEvent.objects.create(
        actor=actor,
        action=action,
        object_type=obj.__class__.__name__,
        object_id=str(obj.pk),
        data=data,
    )
