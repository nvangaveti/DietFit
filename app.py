import os
import streamlit as st
from PIL import Image
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Imports from modular utilities
from utils.storage import load_user, save_user
from graph import app_graph

# Configure Streamlit page layout
st.set_page_config(
    page_title="DietFit - Premium AI Fitness & Diet Advisor",
    page_icon="🥗",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inline UI widget helpers
def ui_macro_card(label: str, value: float, unit: str, color: str = "#6366f1"):
    st.markdown(f"""
        <div class="macro-card">
            <div class="macro-val" style="color: {color};">{value}<span style="font-size: 1.1rem; font-weight: 400; color: #94a3b8;"> {unit}</span></div>
            <div class="macro-lbl">{label}</div>
        </div>
    """, unsafe_allow_html=True)

def clean_recipe_text(text: str) -> str:
    """
    Cleans up recipe markdown text to prevent unclosed headers or massive text scaling.
    """
    if not text:
        return ""
    text = text.strip()
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        stripped_line = line.strip()
        if stripped_line.startswith("#"):
            content = stripped_line.lstrip("#").strip()
            cleaned_lines.append(f"**{content}**")
        else:
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines)

# Load UI styling
if os.path.exists("style.css"):
    with open("style.css", "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# Main Title
st.markdown('<div class="main-title">🥗 DIETFIT</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Simplified AI Fitness Planner & Recipe Personalizer</div>', unsafe_allow_html=True)

# Initialize Session States
for key, val in [("username", None), ("profile", None), ("awaiting_confirmation", False), 
                 ("detected_dish_name", ""), ("analysis_results", None)]:
    if key not in st.session_state:
        st.session_state[key] = val

# Sidebar User Authentication
with st.sidebar:
    st.markdown("### 🔐 User Space")
    if not st.session_state.username:
        username_input = st.text_input("Enter Username", value="", placeholder="e.g., nikhil").strip()
        col1, col2 = st.columns(2)
        if col1.button("Log In") and username_input:
            profile = load_user(username_input)
            if profile:
                st.session_state.username = username_input
                st.session_state.profile = profile
                st.rerun()
            else:
                st.error("User not found. Please register.")
                
        if col2.button("Register") and username_input:
            profile = load_user(username_input)
            if profile:
                st.error("Username already exists. Please login.")
            else:
                st.session_state.username = username_input
                st.session_state.profile = "NEW"
                st.rerun()
    else:
        st.markdown(f"""
            <div class="sidebar-user">
                <strong>Logged in as:</strong><br>
                <span style="font-size: 1.2rem; color: #6366f1; font-weight: 600;">{st.session_state.username}</span>
            </div>
        """, unsafe_allow_html=True)
        
        prof = st.session_state.profile
        if isinstance(prof, dict):
            st.markdown(f"**Goal:** {prof.get('goal', '').replace('_', ' ').title()}")
            st.markdown(f"**Diet:** {prof.get('diet_type', '').title()}")
            st.markdown(f"**Weight:** {prof.get('weight_kg')} kg")
            st.markdown(f"**Height:** {prof.get('height_cm')} cm")
            
        if st.sidebar.button("Logout"):
            st.session_state.username = None
            st.session_state.profile = None
            st.session_state.awaiting_confirmation = False
            st.session_state.detected_dish_name = ""
            st.session_state.analysis_results = None
            st.rerun()

# Application Flow logic
if not st.session_state.username:
    st.info("👈 Enter your username in the sidebar to log in or register a new profile.")
    
elif st.session_state.profile == "NEW":
    st.markdown('<h3 class="section-header">🆕 User Registration & Target Calibration</h3>', unsafe_allow_html=True)
    with st.form("registration_form"):
        col1, col2 = st.columns(2)
        with col1:
            gender = st.selectbox("Gender", ["Male", "Female"])
            age = st.number_input("Age (years)", min_value=1, max_value=120, value=25)
            height = st.number_input("Height (cm)", min_value=50.0, max_value=250.0, value=175.0)
            weight = st.number_input("Weight (kg)", min_value=10.0, max_value=300.0, value=70.0)
        with col2:
            activity = st.selectbox("Activity Level", ["Sedentary", "Lightly Active", "Moderately Active", "Very Active", "Extra Active"])
            goal = st.selectbox("Fitness Goal", ["Lose Fat", "Build Muscle", "Maintain"])
            diet = st.selectbox("Diet Type", ["Balanced", "Vegan", "Keto", "Low Carb"])
        submit_reg = st.form_submit_button("Calibrate Target Macros & Save")
        
    if submit_reg:
        with st.spinner("Calibrating targets with multi-agent calculator..."):
            input_state = {
                "status": "calibrate",
                "weight_kg": weight,
                "height_cm": height,
                "age": age,
                "gender": gender.lower(),
                "activity_level": activity.lower(),
                "goal": goal.lower(),
                "diet_type": diet.lower()
            }
            output_state = app_graph.invoke(input_state)
            new_profile = {
                "goal": goal.lower(),
                "diet_type": diet.lower(),
                "weight_kg": weight,
                "height_cm": height,
                "age": age,
                "gender": gender.lower(),
                "activity_level": activity.lower(),
                "calorie_target": output_state.get("calorie_target"),
                "protein_target": output_state.get("protein_target"),
                "carb_target": output_state.get("carb_target"),
                "fat_target": output_state.get("fat_target")
            }
            save_user(st.session_state.username, new_profile)
            st.session_state.profile = new_profile
            st.rerun()

else:
    prof = st.session_state.profile
    # Auto-calibrate if values are missing
    if not all(prof.get(k) for k in ["calorie_target", "protein_target", "carb_target", "fat_target"]):
        st.warning("⚠️ Calibrating incomplete profile...")
        input_state = {
            "status": "calibrate",
            "weight_kg": float(prof.get("weight_kg", 70.0)),
            "height_cm": float(prof.get("height_cm", 170.0)),
            "age": int(prof.get("age", 25)),
            "gender": prof.get("gender", "male"),
            "activity_level": prof.get("activity_level", "sedentary"),
            "goal": prof.get("goal", "maintain"),
            "diet_type": prof.get("diet_type", "balanced")
        }
        output_state = app_graph.invoke(input_state)
        calibrated_prof = input_state.copy()
        calibrated_prof.update({
            "calorie_target": output_state.get("calorie_target"),
            "protein_target": output_state.get("protein_target"),
            "carb_target": output_state.get("carb_target"),
            "fat_target": output_state.get("fat_target")
        })
        save_user(st.session_state.username, calibrated_prof)
        st.session_state.profile = calibrated_prof
        st.rerun()
        
    # Target Dashboard
    st.markdown('<h4 class="section-header">🎯 Your Daily Calorie & Macronutrient Targets</h4>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1: ui_macro_card("Calories", prof.get("calorie_target"), "kcal", "#3b82f6")
    with c2: ui_macro_card("Protein", prof.get("protein_target"), "g", "#10b981")
    with c3: ui_macro_card("Carbs", prof.get("carb_target"), "g", "#f59e0b")
    with c4: ui_macro_card("Fat", prof.get("fat_target"), "g", "#ec4899")
        
    # Calorie Budget customizing
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<h5>🍽️ Customize Remaining Budget for this Meal</h5>', unsafe_allow_html=True)
    daily_cal_target = float(prof.get("calorie_target", 2000.0))
    meal_calorie_budget = st.number_input("Enter remaining calories left to fill today (kcal)", min_value=100.0, max_value=daily_cal_target, value=daily_cal_target, step=50.0)
    scale = meal_calorie_budget / daily_cal_target if daily_cal_target > 0 else 1.0
    
    custom_prof = prof.copy()
    custom_prof.update({
        "calorie_target": meal_calorie_budget,
        "protein_target": round(float(prof.get("protein_target", 150.0)) * scale, 1),
        "carb_target": round(float(prof.get("carb_target", 200.0)) * scale, 1),
        "fat_target": round(float(prof.get("fat_target", 70.0)) * scale, 1)
    })
    
    st.markdown(f"**Remaining Targets:** `{custom_prof['calorie_target']} kcal` | `Protein: {custom_prof['protein_target']}g` | `Carbs: {custom_prof['carb_target']}g` | `Fat: {custom_prof['fat_target']}g`")
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Upload and Analyze Flow
    st.markdown('<h4 class="section-header">📸 Analyze & Personalize Your Dish</h4>', unsafe_allow_html=True)
    uploaded_file = st.file_uploader("Upload a photo of your meal (JPG, JPEG, PNG)", type=["jpg", "jpeg", "png"])
    
    def process_analysis(dish):
        with st.spinner("Fetching details with multi-agent coordination..."):
            input_state = {
                "status": "analyze",
                "username": st.session_state.username,
                "goal": custom_prof.get("goal"),
                "diet_type": custom_prof.get("diet_type"),
                "calorie_target": custom_prof.get("calorie_target"),
                "protein_target": custom_prof.get("protein_target"),
                "carb_target": custom_prof.get("carb_target"),
                "fat_target": custom_prof.get("fat_target"),
                "dish_name": dish
            }
            res_state = app_graph.invoke(input_state)
            
            st.session_state.analysis_results = {
                "dish_name": res_state.get("dish_name"),
                "macros": {
                    "calories": res_state.get("dish_calories"),
                    "protein": res_state.get("dish_protein"),
                    "carbs": res_state.get("dish_carbs"),
                    "fat": res_state.get("dish_fat")
                },
                "recipe_info": {
                    "original_recipe": res_state.get("original_recipe"),
                    "recipe_source_url": res_state.get("recipe_source_url")
                },
                "advice": {
                    "verdict": res_state.get("verdict"),
                    "adjusted_recipe": res_state.get("adjusted_recipe"),
                    "explanation": res_state.get("explanation")
                }
            }

    if uploaded_file:
        col_img, col_act = st.columns([1, 1.5])
        with col_img:
            st.markdown('<div class="glass-card">', unsafe_allow_html=True)
            st.image(Image.open(uploaded_file), caption="Uploaded Meal Photo", use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
        with col_act:
            if st.button("Identify Dish & Analyze Macros"):
                st.session_state.awaiting_confirmation = False
                st.session_state.analysis_results = None
                with st.spinner("Analyzing image with multi-agent orchestration..."):
                    input_state = {
                        "status": "analyze",
                        "username": st.session_state.username,
                        "goal": custom_prof.get("goal"),
                        "diet_type": custom_prof.get("diet_type"),
                        "calorie_target": custom_prof.get("calorie_target"),
                        "protein_target": custom_prof.get("protein_target"),
                        "carb_target": custom_prof.get("carb_target"),
                        "fat_target": custom_prof.get("fat_target"),
                        "image_path": uploaded_file
                    }
                    res_state = app_graph.invoke(input_state)
                    
                    conf = res_state.get("vision_confidence", 0.0)
                    dish_name = res_state.get("dish_name", "Unknown Dish")
                    st.session_state.detected_dish_name = dish_name
                    
                    if conf < 0.70:
                        st.session_state.awaiting_confirmation = True
                        st.warning(f"Low confidence ({conf:.1%}) identifying '{dish_name}'. Please verify the name below.")
                    else:
                        st.session_state.analysis_results = {
                            "dish_name": dish_name,
                            "macros": {
                                "calories": res_state.get("dish_calories"),
                                "protein": res_state.get("dish_protein"),
                                "carbs": res_state.get("dish_carbs"),
                                "fat": res_state.get("dish_fat")
                            },
                            "recipe_info": {
                                "original_recipe": res_state.get("original_recipe"),
                                "recipe_source_url": res_state.get("recipe_source_url")
                            },
                            "advice": {
                                "verdict": res_state.get("verdict"),
                                "adjusted_recipe": res_state.get("adjusted_recipe"),
                                "explanation": res_state.get("explanation")
                            }
                        }
                        st.rerun()

            if st.session_state.awaiting_confirmation:
                confirmed_name = st.text_input("Verify or Edit Dish Name", value=st.session_state.detected_dish_name)
                if st.button("Confirm Name & Process Recipe") and confirmed_name:
                    st.session_state.awaiting_confirmation = False
                    process_analysis(confirmed_name)
                    st.rerun()

            # Display Nutrients
            if st.session_state.analysis_results:
                res = st.session_state.analysis_results
                st.success(f"Analysis complete for **{res['dish_name']}**!")
                verdict = res["advice"].get("verdict", "")
                badge_class = "badge-fits" if "Fits" in verdict else "badge-mod"
                badge_icon = "✅" if "Fits" in verdict else "⚠️"
                st.markdown(f'<div class="{badge_class}">{badge_icon} {verdict}</div>', unsafe_allow_html=True)
                st.markdown("<br>", unsafe_allow_html=True)
                
                st.markdown("**Found Dish Nutrients (USDA lookup):**")
                col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                col_m1.metric("Calories", f"{res['macros'].get('calories')} kcal")
                col_m2.metric("Protein", f"{res['macros'].get('protein')} g")
                col_m3.metric("Carbs", f"{res['macros'].get('carbs')} g")
                col_m4.metric("Fat", f"{res['macros'].get('fat')} g")

        # Side-by-Side Detailed Recipes Display
        if st.session_state.analysis_results:
            res = st.session_state.analysis_results
            st.markdown('<h4 class="section-header">🍽️ Diet Advisor Portions & Recipe Personalization</h4>', unsafe_allow_html=True)
            col_orig, col_adj = st.columns(2)
            
            with col_orig:
                st.markdown('<div class="glass-card">', unsafe_allow_html=True)
                st.subheader("Original Dish Recipe Profile")
                st.markdown(clean_recipe_text(res["recipe_info"].get("original_recipe", "No recipe found.")))
                if res["recipe_info"].get("recipe_source_url"):
                    st.markdown(f"[Recipe Source URL]({res['recipe_info'].get('recipe_source_url')})")
                st.markdown('</div>', unsafe_allow_html=True)
                
            with col_adj:
                st.markdown('<div class="glass-card" style="border-color: rgba(99, 102, 241, 0.3);">', unsafe_allow_html=True)
                st.subheader("Personalized Adjusted Recipe")
                st.markdown(clean_recipe_text(res["advice"].get("adjusted_recipe", "No adjusted recipe content found.")))
                st.markdown('</div>', unsafe_allow_html=True)
                
            st.markdown('<div class="glass-card">', unsafe_allow_html=True)
            st.subheader("Advisor Analysis & Explanation")
            st.markdown(clean_recipe_text(res["advice"].get("explanation", "")))
            st.markdown('</div>', unsafe_allow_html=True)
