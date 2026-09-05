"""Input Validation & Sanitization Engine for DietFit.

Provides strict validators and sanitizers to defend against:
- SQL & NoSQL injection (defensive character stripping / structural boundaries)
- OS Command injection (strictly disallows shell metacharacters `& ; | ` $ > < \n \r`)
- Cross-Site Scripting (XSS) & Script/HTML injection (HTML escaping & tag stripping)
- Unsafe file upload attacks (magic byte validation, dimension checks, MIME enforcement, size caps)
- Prototype pollution / parameter tampering
- Strict numeric boundary validation
"""

import re
import html
import io
from typing import Tuple, Optional, Any
from PIL import Image
from utils.security_logger import log_security_event, EVENT_VALIDATION_FAILURE

# ==========================================
# CONSTANTS & POLICIES
# ==========================================
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB maximum upload limit
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
ALLOWED_MIME_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGE_DIMENSION = 4096  # prevent image decompression bombs (pixel flood attacks)
MIN_IMAGE_DIMENSION = 10

# Regex patterns for sanitization & strict matching
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
ALPHANUMERIC_SPACE_REGEX = re.compile(r"^[a-zA-Z0-9\s\-',.()]+$")
DISH_NAME_REGEX = re.compile(r"^[a-zA-Z0-9\s\-',./&()]+$")
COMMAND_INJECTION_CHARS = re.compile(r"[`$&|;><\n\r\\{}]")


class ValidationError(ValueError):
    """Raised when an input fails strict schema or security validation."""
    pass


# ==========================================
# 1. TEXT SANITIZATION & SCRIPT INJECTION DEFENSE
# ==========================================
def sanitize_text(value: Optional[str], max_length: int = 500) -> str:
    """Sanitizes text by stripping null bytes, controlling length, and escaping HTML entities.
    
    Prevents XSS and HTML/script injection in Markdown or DOM rendering contexts.
    """
    if not value:
        return ""
    # Strip null bytes and control chars (prevent truncation attacks)
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value).strip())
    # HTML escape dangerous characters (<, >, &, ", ')
    escaped = html.escape(cleaned)
    # Enforce maximum length
    return escaped[:max_length]


def sanitize_for_prompt(value: Optional[str], max_length: int = 200) -> str:
    """Sanitizes user input destined for LLM prompts or third-party APIs.
    
    Strips command injection metacharacters, prompt escape blocks, and excessive whitespace.
    """
    if not value:
        return ""
    # Remove command injection symbols and potential prompt-breaking brackets
    cleaned = str(value).strip()
    cleaned = COMMAND_INJECTION_CHARS.sub("", cleaned)
    # Strip markdown block delimiters to prevent prompt jailbreaking
    cleaned = cleaned.replace("```", "").replace("---", " - ")
    # Replace multiple spaces with single space
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:max_length].strip()


def validate_email(email: Optional[str]) -> str:
    """Validates email format strictly. Returns normalized lower-case email."""
    if not email:
        raise ValidationError("Email address cannot be empty.")
    clean = str(email).strip().lower()
    if len(clean) > 254:
        raise ValidationError("Email exceeds maximum allowable length of 254 characters.")
    if not EMAIL_REGEX.match(clean):
        raise ValidationError("Invalid email address format.")
    return clean


def validate_name(name: Optional[str]) -> str:
    """Validates user full name, preventing script or special command characters."""
    if not name:
        raise ValidationError("Name cannot be empty.")
    clean = str(name).strip()
    if len(clean) < 2 or len(clean) > 80:
        raise ValidationError("Name must be between 2 and 80 characters.")
    if COMMAND_INJECTION_CHARS.search(clean) or "<" in clean or ">" in clean:
        raise ValidationError("Name contains illegal or unsafe characters.")
    return html.escape(clean)


def validate_dish_name(dish_name: Optional[str]) -> str:
    """Validates food dish name, rejecting command injections or suspicious payloads."""
    if not dish_name:
        raise ValidationError("Dish name cannot be empty.")
    clean = str(dish_name).strip()
    if len(clean) > 120:
        raise ValidationError("Dish name exceeds maximum length of 120 characters.")
    if COMMAND_INJECTION_CHARS.search(clean) or "<" in clean or ">" in clean:
        raise ValidationError("Dish name contains prohibited characters or command symbols.")
    return clean


# ==========================================
# 2. NUMERIC & PROFILE BOUNDARY VALIDATION
# ==========================================
VALID_GOALS = {"lose_fat", "lose fat", "build_muscle", "build muscle", "maintain"}
VALID_DIETS = {"balanced", "vegan", "keto", "low_carb", "low carb"}
VALID_GENDERS = {"male", "female"}
VALID_ACTIVITIES = {
    "sedentary", "lightly active", "moderately active", "very active", "extra active",
    "lightly_active", "moderately_active", "very_active", "extra_active"
}


def validate_profile_inputs(
    weight: float,
    height: float,
    age: int,
    gender: str,
    activity: str,
    goal: str,
    diet: str
) -> dict:
    """Enforces strict range checks and enum memberships for profile parameters."""
    try:
        w = float(weight)
        h = float(height)
        a = int(age)
    except (ValueError, TypeError):
        raise ValidationError("Weight, height, and age must be valid numeric values.")
        
    if not (20.0 <= w <= 400.0):
        raise ValidationError("Weight must be between 20 kg and 400 kg.")
    if not (50.0 <= h <= 280.0):
        raise ValidationError("Height must be between 50 cm and 280 cm.")
    if not (5 <= a <= 125):
        raise ValidationError("Age must be between 5 and 125 years.")
        
    g_clean = str(gender).strip().lower()
    if g_clean not in VALID_GENDERS:
        raise ValidationError(f"Invalid gender specified. Must be one of: {sorted(list(VALID_GENDERS))}")
        
    act_clean = str(activity).strip().lower()
    if act_clean not in VALID_ACTIVITIES:
        raise ValidationError(f"Invalid activity level: {activity}")
        
    goal_clean = str(goal).strip().lower()
    if goal_clean not in VALID_GOALS:
        raise ValidationError(f"Invalid goal: {goal}")
        
    diet_clean = str(diet).strip().lower()
    if diet_clean not in VALID_DIETS:
        raise ValidationError(f"Invalid diet type: {diet}")
        
    return {
        "weight_kg": round(w, 2),
        "height_cm": round(h, 2),
        "age": a,
        "gender": g_clean,
        "activity_level": act_clean,
        "goal": goal_clean,
        "diet_type": diet_clean
    }


# ==========================================
# 3. SECURE FILE UPLOAD VALIDATION
# ==========================================
def validate_uploaded_image(file_obj) -> Tuple[bool, str, Optional[Image.Image]]:
    """Strictly validates uploaded image file using magic bytes, MIME, size, and dimension checks.
    
    Guards against:
    - Executable masquerading as images (Polyglot files)
    - Decompression bombs (huge pixel dimensions)
    - Oversized payloads (Denial of Service)
    - Corrupt or malicious image structures
    
    Returns:
        (is_valid: bool, message: str, opened_image: Optional[Image.Image])
    """
    if file_obj is None:
        return False, "No file uploaded.", None
        
    # 1. File Size Validation
    try:
        # Check size if available
        size = getattr(file_obj, "size", None)
        if size is None:
            pos = file_obj.tell()
            file_obj.seek(0, io.SEEK_END)
            size = file_obj.tell()
            file_obj.seek(pos)
            
        if size > MAX_UPLOAD_SIZE_BYTES:
            return False, f"File exceeds maximum allowed size of {MAX_UPLOAD_SIZE_BYTES // (1024*1024)}MB.", None
        if size < 100:
            return False, "File is too small to be a valid image.", None
    except Exception as e:
        return False, f"Could not inspect file size: {e}", None
        
    # 2. Magic Byte & Deep Format Inspection via Pillow
    try:
        pos = file_obj.tell()
        # Read header and verify image structure
        image = Image.open(file_obj)
        image.verify()  # Verifies file integrity without decoding whole stream
        
        format_detected = image.format
        if not format_detected or format_detected.upper() not in ALLOWED_IMAGE_FORMATS:
            return False, f"Prohibited image format '{format_detected}'. Allowed formats: JPG, PNG, WEBP.", None
            
        # Re-open after verify() closes/invalidates stream pointer
        file_obj.seek(pos)
        decoded_image = Image.open(file_obj)
        
        # 3. Dimension Validation (Decompression Bomb Protection)
        width, height = decoded_image.size
        if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
            return False, f"Image dimensions ({width}x{height}) exceed maximum allowed {MAX_IMAGE_DIMENSION}x{MAX_IMAGE_DIMENSION}px.", None
        if width < MIN_IMAGE_DIMENSION or height < MIN_IMAGE_DIMENSION:
            return False, "Image dimensions are suspiciously small.", None
            
        # 4. Total Pixel Cap
        total_pixels = width * height
        if total_pixels > 16_000_000:  # ~16 Megapixels
            return False, "Image pixel count exceeds maximum allowable memory safety threshold.", None
            
        file_obj.seek(pos)
        return True, "Image verified successfully.", decoded_image
        
    except Exception as e:
        return False, f"Invalid or corrupted image file: {e}", None
