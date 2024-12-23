import torch
import torchaudio
from transformers import pipeline
from moviepy.editor import VideoFileClip, AudioFileClip
import speech_recognition as sr
from gtts import gTTS
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from .models import MediaFile
from .forms import MediaUploadForm
import os
from pathlib import Path
import subprocess

# Check and initialize ffmpeg
def initialize_ffmpeg():
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        if result.returncode == 0:
            print("FFmpeg found in system PATH") 
            return True
    except FileNotFoundError:
        print("FFmpeg not found in system PATH, checking common locations...")
        
        # For Windows, try common installation locations
        common_paths = [
            r'C:\ffmpeg\bin\ffmpeg.exe',
            r'C:\Program Files\ffmpeg\bin\ffmpeg.exe', 
            r'C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe'
]
        
        for path in common_paths:
            if os.path.exists(path):
                print(f"FFmpeg found at: {path}")
                # Add the directory containing ffmpeg to the system PATH
                ffmpeg_dir = os.path.dirname(path)
                os.environ['PATH'] = ffmpeg_dir + os.pathsep + os.environ['PATH']
                # Also set the full path to ffmpeg
                os.environ['FFMPEG_BINARY'] = path
                return True
        
        print("FFmpeg not found in common locations")
        return False
    except Exception as e:
        print(f"Error checking FFmpeg: {str(e)}")
        return False

# Initialize device and check ffmpeg
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
ffmpeg_available = initialize_ffmpeg()

if not ffmpeg_available:
    print("WARNING: FFmpeg is not available. Please install FFmpeg first.")

def load_models():
    try:
        # Load Silero STT model
        model, decoder, utils = torch.hub.load(repo_or_dir='snakers4/silero-models',
                                             model='silero_stt',
                                             language='en',
                                             device=device)
        print("Models loaded successfully")
        return model, decoder, utils
    except Exception as e:
        print(f"Error loading models: {str(e)}")
        return None, None, None

# Initialize models
stt_model, decoder, utils = load_models()

def handle_audio_to_text(audio_path, output_path):
    try:
        if not stt_model or not decoder or not utils:
            raise Exception("Speech-to-text model not properly initialized")

        # Get utility functions from Silero
        (read_batch, split_into_batches, read_audio, prepare_model_input) = utils
        
        print(f"Processing audio file: {audio_path}")
        
        # Read audio using torchaudio instead of ffmpeg
        waveform, sample_rate = torchaudio.load(audio_path)
        
        # Convert to mono if stereo
        if waveform.shape[0] > 1:
            waveform = torch.mean(waveform, dim=0, keepdim=True)
        
        # Resample to 16kHz if needed
        if sample_rate != 16000:
            resampler = torchaudio.transforms.Resample(sample_rate, 16000)
            waveform = resampler(waveform)
        
        # Prepare input for model
        input_data = waveform.to(device)
        
        # Get transcription
        output = stt_model(input_data)
        transcribed_text = decoder(output[0].cpu())
        
        print(f"Transcription completed: {transcribed_text[:100]}...")
        
        # Ensure the output directory exists
        output_dir = os.path.dirname(output_path)
        os.makedirs(output_dir, exist_ok=True)
        
        # Save transcribed text
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(transcribed_text)
        
        print(f"Successfully saved transcription to: {output_path}")
        return output_path
        
    except Exception as e:
        print(f"Error in audio-to-text conversion: {str(e)}")
        raise Exception(f"Failed to convert audio to text: {str(e)}")

def handle_video_audio_translation(video_path, target_language, output_path):
    try:
        if not ffmpeg_available:
            raise Exception("FFmpeg is not installed. Please install FFmpeg first.")
            
        # Extract audio from video using moviepy
        video = VideoFileClip(video_path)
        audio = video.audio
        
        # Create temp directory
        temp_dir = Path(settings.MEDIA_ROOT) / 'temp'
        temp_dir.mkdir(exist_ok=True)
        
        # Save temporary audio file
        temp_audio_path = temp_dir / f'temp_audio_{os.path.basename(video_path)}.wav'
        audio.write_audiofile(str(temp_audio_path), codec='pcm_s16le')
        
        # Convert audio to text using Silero STT model
        waveform, sample_rate = torchaudio.load(str(temp_audio_path))
        if waveform.shape[0] > 1:
            waveform = torch.mean(waveform, dim=0, keepdim=True)
        if sample_rate != 16000:
            resampler = torchaudio.transforms.Resample(sample_rate, 16000)
            waveform = resampler(waveform)
        
        input_data = waveform.to(device)
        output = stt_model(input_data)
        text = decoder(output[0].cpu())
        
        # Translate text using gTTS
        tts = gTTS(text=text, lang=target_language)
        translated_audio_path = temp_dir / f'translated_{os.path.basename(video_path)}.mp3'
        tts.save(str(translated_audio_path))
        
        # Combine video with translated audio
        video = video.set_audio(AudioFileClip(str(translated_audio_path)))
        video.write_videofile(str(output_path), codec='libx264', audio_codec='aac')
        
        # Cleanup
        video.close()
        audio.close()
        temp_audio_path.unlink(missing_ok=True)
        translated_audio_path.unlink(missing_ok=True)
        
        return output_path
        
    except Exception as e:
        print(f"Error in video translation: {str(e)}")
        return None

def process_file(request, file_id):
    media = get_object_or_404(MediaFile, id=file_id)
    
    try:
        processed_dir = Path(settings.MEDIA_ROOT) / 'processed'
        processed_dir.mkdir(exist_ok=True)
        
        # Update status to processing
        media.status = 'processing'
        media.save()
        
        if media.file_type == 'audio':
            # Process audio file
            output_path = processed_dir / f'transcript_{media.id}.txt'
            
            try:
                processed_file = handle_audio_to_text(media.file.path, output_path)
                
                if processed_file:
                    media.processed_file = str(Path(processed_file).relative_to(settings.MEDIA_ROOT))
                    media.status = 'completed'
                    media.save()
                    messages.success(request, 'Audio transcribed successfully! Click download to get the text file.')
                else:
                    raise Exception("Processing failed - no output file generated")
                    
            except Exception as e:
                media.status = 'failed'
                media.error_message = f'Processing error: {str(e)}'
                media.save()
                messages.error(request, f'Error processing file: {str(e)}')
        
        elif media.file_type == 'video':

            # Process video file to extract audio
            output_path = processed_dir / f'audio_{media.id}.mp3'
            




            try:
                video = VideoFileClip(media.file.path)
                audio = video.audio
                
                # Extract and save audio as MP3
                audio.write_audiofile(
                    str(output_path),
                    codec='mp3',
                    bitrate='192k',
                    ffmpeg_params=["-q:a", "0"]
                )
                
                # Clean up resources
                video.close()
                audio.close()
                
                # Update media record with processed file
                media.processed_file = str(Path(output_path).relative_to(settings.MEDIA_ROOT))
                media.status = 'completed'
                media.save()
                messages.success(request, 'Video converted to MP3 successfully!')
                
            except Exception as e:
                media.status = 'failed'
                media.error_message = f'Processing error: {str(e)}'
                media.save()
                messages.error(request, f'Error processing file: {str(e)}')
                
    except Exception as e:
        media.status = 'failed'
        media.error_message = str(e)
        media.save()
        messages.error(request, f'Error processing file: {str(e)}')
    

    return redirect('file_list')
def home(request):
    """Home view that shows the upload form"""
    return upload_file(request)

def upload_file(request):
    if request.method == 'POST':
        form = MediaUploadForm(request.POST, request.FILES)
        if form.is_valid():
            # Validate file size
            if request.FILES['file'].size > 500 * 1024 * 1024:
                messages.error(request, 'File size must be less than 500MB')
                return render(request, 'convertor/upload.html', {'form': form})
            
            media = form.save()
            
            # If it's a text file, process it immediately
            if media.file_type == 'text':
                try:
                    processed_dir = Path(settings.MEDIA_ROOT) / 'processed'
                    processed_dir.mkdir(exist_ok=True)
                    
                    output_path = processed_dir / f'audio_{media.id}.mp3'
                    processed_file = handle_text_to_speech(
                        media.file.path, 
                        output_path,
                        media.target_language or 'en'
                    )
                    
                    if processed_file:
                        media.processed_file = str(Path(processed_file).relative_to(settings.MEDIA_ROOT))
                        media.save()
                        messages.success(request, 'Text converted to audio successfully!')
                        return redirect('file_list')
                    else:
                        messages.error(request, 'Error converting text to audio')
                except Exception as e:
                    messages.error(request, f'Error processing file: {str(e)}')
            else:
                # For video and audio files, redirect to processing
                messages.info(request, 'File uploaded successfully. Processing...')
                return redirect('process_file', file_id=media.id)
    else:
        form = MediaUploadForm()
    
    return render(request, 'convertor/upload.html', {'form': form})

def file_list(request):
    files = MediaFile.objects.all().order_by('-created_at')
    return render(request, 'convertor/file_list.html', {'files': files})

def delete_file(request, file_id):
    media = get_object_or_404(MediaFile, id=file_id)
    
    try:
        # Delete the physical files
        if media.file:
            file_path = Path(media.file.path)
            if file_path.exists():
                file_path.unlink()
        
        if media.processed_file:
            processed_path = Path(media.processed_file.path)
            if processed_path.exists():
                processed_path.unlink()
        
        # Delete the database record
        media.delete()
        messages.success(request, 'File deleted successfully!')
    except Exception as e:
        messages.error(request, f'Error deleting file: {str(e)}')
    
    return redirect('file_list')

def download_file(request, file_id):
    media = get_object_or_404(MediaFile, id=file_id)
    
    if not media.processed_file:
        messages.error(request, 'No processed file available for download')
        return redirect('file_list')
    
    try:
        file_path = os.path.join(settings.MEDIA_ROOT, str(media.processed_file))
        if os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                response = HttpResponse(f.read())
                
                # Set the content type based on file extension
                if file_path.endswith('.txt'):
                    response['Content-Type'] = 'text/plain'
                elif file_path.endswith('.mp3'):
                    response['Content-Type'] = 'audio/mpeg'
                elif file_path.endswith('.mp4'):
                    response['Content-Type'] = 'video/mp4'
                
                # Set filename for download
                filename = os.path.basename(file_path)
                response['Content-Disposition'] = f'attachment; filename="{filename}"'
                
                return response
        else:
            messages.error(request, 'File not found')
            return redirect('file_list')
    except Exception as e:
        messages.error(request, f'Error downloading file: {str(e)}')
        return redirect('file_list')

def handle_text_to_speech(text_file_path, output_path, language='en'):
    try:
        # Read text file
        with open(text_file_path, 'r', encoding='utf-8') as f:
            text = f.read()
        
        # Convert text to speech using gTTS
        tts = gTTS(text=text, lang=language)
        
        # Ensure output directory exists
        output_dir = os.path.dirname(output_path)
        os.makedirs(output_dir, exist_ok=True)
        
        # Save the audio file
        tts.save(str(output_path))
        
        return str(output_path)
    except Exception as e:
        print(f"Error in text-to-speech conversion: {str(e)}")
        return None

def handle_video_to_audio(video_path, output_path):
    try:
        if not ffmpeg_available:
            raise Exception("FFmpeg is not installed")
            
        # Load video and extract audio using moviepy
        video = VideoFileClip(video_path)
        audio = video.audio
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Write audio to MP3 file with high quality settings
        audio.write_audiofile(
            output_path,
            codec='mp3',
            bitrate='192k',
            ffmpeg_params=["-q:a", "0"]
        )
        
        # Clean up resources
        video.close()
        audio.close()
        
        return output_path
        
    except Exception as e:
        print(f"Error extracting audio: {str(e)}")
        return None
