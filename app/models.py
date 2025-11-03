
# django_app/models.py
from django.db import models
from cloudinary.models import CloudinaryField

class EmbeddingRecord(models.Model):
    user_id = models.CharField(max_length=100)
    bot_id = models.CharField(max_length=100)
    index_id = models.CharField(max_length=100, unique=True)
    file_name = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    pinecone_namespace = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.file_name} ({self.user_id})"
