from django.conf import settings
from django.db import models


class FavoriteCurrency(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='favorite_currencies',
    )
    code = models.CharField(max_length=3)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'code'], name='unique_user_currency_favorite'),
        ]
        ordering = ['code']

    def __str__(self):
        return f'{self.user_id}:{self.code}'


class AdminNotification(models.Model):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='admin_notifications',
    )
    message = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.recipient_id}:{self.message[:32]}'


class ExchangeAlert(models.Model):
    CONDITION_ABOVE = 'above'
    CONDITION_BELOW = 'below'
    CONDITION_CHOICES = [
        (CONDITION_ABOVE, 'Por encima de'),
        (CONDITION_BELOW, 'Por debajo de'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='exchange_alerts',
    )
    base_currency = models.CharField(max_length=3)
    quote_currency = models.CharField(max_length=3)
    condition = models.CharField(max_length=10, choices=CONDITION_CHOICES)
    target_rate = models.DecimalField(max_digits=12, decimal_places=6)
    is_active = models.BooleanField(default=True)
    is_triggered = models.BooleanField(default=False)
    last_triggered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        pair = f'{self.base_currency}/{self.quote_currency}'
        return f'{self.user_id}:{pair}:{self.condition}:{self.target_rate}'


class UserAlertNotification(models.Model):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='user_alert_notifications',
    )
    alert = models.ForeignKey(
        ExchangeAlert,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications',
    )
    message = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.recipient_id}:{self.message[:32]}'
