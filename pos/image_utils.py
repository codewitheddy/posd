"""
Image processing utilities for optimal performance
"""
from PIL import Image
from io import BytesIO
from django.core.files.uploadedfile import InMemoryUploadedFile
import sys
import os


class ImageOptimizer:
    """Optimize images for web performance"""
    
    # Image size configurations
    SIZES = {
        'thumbnail': (150, 150),      # For lists/grids
        'small': (300, 300),          # For cards
        'medium': (600, 600),         # For detail views
        'large': (1200, 1200),        # For full view
    }
    
    # Quality settings
    JPEG_QUALITY = 85
    WEBP_QUALITY = 80
    PNG_QUALITY = 85
    
    # Max file size (5MB)
    MAX_FILE_SIZE = 5 * 1024 * 1024
    
    @staticmethod
    def optimize_image(image_file, max_size=(1200, 1200), quality=85):
        """
        Optimize an uploaded image
        - Resize if too large
        - Compress
        - Convert to RGB if needed
        - Return optimized file
        """
        try:
            # Open image
            img = Image.open(image_file)
            
            # Convert RGBA to RGB (for JPEG compatibility)
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Resize if larger than max_size
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Save to BytesIO
            output = BytesIO()
            img.save(output, format='JPEG', quality=quality, optimize=True)
            output.seek(0)
            
            # Create new InMemoryUploadedFile
            optimized_file = InMemoryUploadedFile(
                output,
                'ImageField',
                f"{os.path.splitext(image_file.name)[0]}.jpg",
                'image/jpeg',
                sys.getsizeof(output),
                None
            )
            
            return optimized_file
            
        except Exception as e:
            print(f"Error optimizing image: {e}")
            return image_file
    
    @staticmethod
    def create_thumbnail(image_path, size=(150, 150)):
        """
        Create a thumbnail from an existing image
        Returns PIL Image object
        """
        try:
            img = Image.open(image_path)
            
            # Convert to RGB if needed
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Create thumbnail
            img.thumbnail(size, Image.Resampling.LANCZOS)
            
            return img
            
        except Exception as e:
            print(f"Error creating thumbnail: {e}")
            return None
    
    @staticmethod
    def validate_image(image_file):
        """
        Validate uploaded image
        Returns (is_valid, error_message)
        """
        # Check file size
        if image_file.size > ImageOptimizer.MAX_FILE_SIZE:
            return False, f"Image too large. Maximum size is {ImageOptimizer.MAX_FILE_SIZE / (1024*1024):.1f}MB"
        
        # Check if it's a valid image
        try:
            img = Image.open(image_file)
            img.verify()
            return True, None
        except Exception as e:
            return False, f"Invalid image file: {str(e)}"
    
    @staticmethod
    def get_image_dimensions(image_file):
        """Get image width and height"""
        try:
            img = Image.open(image_file)
            return img.size
        except:
            return None, None


def generate_upload_path(instance, filename, folder='products'):
    """
    Generate organized upload path
    Format: media/{folder}/{year}/{month}/{filename}
    """
    from datetime import datetime
    now = datetime.now()
    ext = filename.split('.')[-1]
    
    # Create unique filename
    unique_filename = f"{now.strftime('%Y%m%d_%H%M%S')}_{instance.pk or 'new'}.{ext}"
    
    return f"{folder}/{now.year}/{now.month:02d}/{unique_filename}"
