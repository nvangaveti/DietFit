from state import AgentState
from utils.gemini import analyze_dish_image

def vision_agent(state: AgentState) -> dict:
    """
    Vision agent that analyzes the image at `image_path` using Gemini Flash
    and updates the state with the identified dish name and confidence score.
    """
    image_path = state.get("image_path")
    if not image_path:
        return {"message": "No image path provided."}
        
    analysis = analyze_dish_image(image_path)
    return {
        "dish_name": analysis.get("dish_name", "Unknown Dish"),
        "vision_confidence": float(analysis.get("confidence", 0.0))
    }
