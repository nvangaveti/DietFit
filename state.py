from typing import TypedDict, Optional, List
class AgentState(TypedDict):
    email: str
    goal:str
    diet_type:str
    weight_kg:float
    height_cm:float
    age:int
    gender:str
    activity_level:str
    calorie_target: Optional[float]
    protein_target:Optional[float]
    carb_target:Optional[float]
    fat_target:Optional[float]
    image_path:Optional[str]
    dish_name:Optional[str]
    vision_confidence:Optional[float]
    dish_calories:Optional[float]
    dish_protein:Optional[float]
    dish_carbs:Optional[float]
    dish_fat:Optional[float]
    original_recipe:Optional[str]
    recipe_source_url:Optional[str]
    adjusted_recipe:Optional[str]
    verdict:Optional[str]
    explanation:Optional[str]
    status:str
    message: Optional[str]