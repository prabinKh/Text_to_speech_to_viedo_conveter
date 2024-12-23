from django import forms
from .models import MediaFile

class MediaUploadForm(forms.ModelForm):
    class Meta:
        model = MediaFile
        fields = ['file', 'file_type', 'source_language', 'target_language']
        widgets = {
            'file': forms.FileInput(attrs={'class': 'form-control'}),
            'file_type': forms.Select(attrs={'class': 'form-control'}),
            'source_language': forms.Select(attrs={'class': 'form-control'}),
            'target_language': forms.Select(attrs={'class': 'form-control'}),
        }
        labels = {
            'file': 'Select File',
            'file_type': 'File Type',
            'source_language': 'Source Language',
            'target_language': 'Target Language'
        }
        help_texts = {
            'file': 'Maximum file size: 500MB',
            'source_language': 'Select the source language of your file',
            'target_language': 'Select the target language for translation'
        }