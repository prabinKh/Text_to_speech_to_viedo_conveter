from django.db import models

class MediaFile(models.Model):
    FILE_TYPES = (
        ('video', 'Video'),
        ('text', 'Text'),
        ('audio', 'Audio')
    )
    
    LANGUAGE_CHOICES = (
        ('en', 'English'),
        ('hi', 'Hindi'),
        ('ne', 'Nepali'),
    )
    
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed')
    )
    
    file = models.FileField(upload_to='uploads/')
    file_type = models.CharField(max_length=5, choices=FILE_TYPES)
    target_language = models.CharField(
        max_length=2, 
        choices=LANGUAGE_CHOICES,
        default='en',
        blank=True
    )
    processed_file = models.FileField(upload_to='processed/', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='pending'
    )
    error_message = models.TextField(blank=True)
    source_language = models.CharField(
        max_length=2, 
        choices=LANGUAGE_CHOICES,
        default='en',
        blank=True
    )
    
    def __str__(self):
        return f"{self.file_type} - {self.created_at}"