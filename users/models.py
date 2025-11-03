from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    pass


class Bot(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="bots")
    bot_name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.bot_name} ({self.user.username})"
