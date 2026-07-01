import os
import json
import google.generativeai as genai
from PIL import Image

def analyze_dish_image(image_input) -> dict:
    """
    Uses Gemini Flash to analyze a food image, returning the dish name and confidence score.
    Returns: {"dish_name": str, "confidence": float}
    """
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY not found in environment variables")
    
    genai.configure(api_key=api_key)
    
    # We can try to use gemini-1.5-flash for maximum stability.
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    try:
        image = Image.open(image_input)
        prompt = (
            "Identify the main food dish in this image. "
            "Respond ONLY with a JSON object containing two fields: "
            "'dish_name' (a string, the common name of the dish) and "
            "'confidence' (a float between 0.0 and 1.0 representing your confidence in this identification)."
        )
        
        response = model.generate_content(
            [prompt, image],
            generation_config={"response_mime_type": "application/json"}
        )
        
        result = json.loads(response.text)
        return {
            "dish_name": result.get("dish_name", "Unknown Dish"),
            "confidence": float(result.get("confidence", 0.5))
        }
    except Exception as e:
        print(f"Gemini Vision API error: {e}")
        return {"dish_name": "Unknown Dish", "confidence": 0.0}

if __name__ == "__main__":
    # Test stub
    import sys
    if len(sys.argv) > 1:
        img_path = sys.argv[1]
        print(f"Analyzing {img_path}...")
        print(analyze_dish_image(img_path))
    else:
        print("Please provide an image path to test.")
