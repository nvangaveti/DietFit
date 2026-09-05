import os
import time
import streamlit as st
from PIL import Image
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Imports from modular utilities
from utils.storage import (
    load_user, save_user, get_user_record, create_user_record,
    delete_user, ResourceOwnershipError, verify_ownership
)
from utils.auth import (
    create_session, validate_session, touch_session,
    SESSION_INACTIVITY_TIMEOUT, SESSION_ABSOLUTE_TIMEOUT
)
from utils.validation import (
    validate_email, validate_name, validate_dish_name,
    validate_profile_inputs, validate_uploaded_image, sanitize_text,
    ValidationError
)
from utils.ratelimit import (
    check_abuse_limit, record_abuse_call, reset_abuse_limit,
    RateLimitExceeded
)
from utils.security_logger import (
    log_security_event,
    EVENT_AUTH_LOGIN_SUCCESS, EVENT_AUTH_LOGIN_FAILURE, EVENT_AUTH_LOCKOUT,
    EVENT_ABUSE_THROTTLED, EVENT_INSECURE_PROTOCOL, sanitize_log_string
)
from utils.email_service import is_smtp_configured
from graph import app_graph

# Environment & Debug Configuration (default False if unset)
DEBUG_MODE = os.environ.get("DEBUG_MODE", "").strip().lower() in ("true", "1", "yes")

# Configure Streamlit page layout
st.set_page_config(
    page_title="DietFit - Personalized Nutrition",
    page_icon="🥗",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Load custom grounded CSS
if os.path.exists("style.css"):
    with open("style.css", "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# Insecure Transport Check (behind production TLS reverse proxy)
try:
    if hasattr(st, "context") and hasattr(st.context, "headers"):
        incoming_proto = str(st.context.headers.get("x-forwarded-proto", "")).lower()
        if incoming_proto == "http":
            log_security_event(
                EVENT_INSECURE_PROTOCOL,
                severity="WARNING",
                actor="visitor",
                action_taken="WARN",
                resource="web_entrypoint",
                details={"header": "x-forwarded-proto: http"}
            )
            st.markdown("""
                <div class="security-banner warning">
                    <span>Security Advisory: Insecure HTTP connection detected. In production, communications must be encrypted over HTTPS.</span>
                </div>
            """, unsafe_allow_html=True)
except Exception:
    pass

# Helper function to render reusable horizontal macro chips
def render_macro_chips(protein: float, carbs: float, fat: float) -> str:
    prot_str = f"{protein:g}" if isinstance(protein, (int, float)) else str(protein)
    carb_str = f"{carbs:g}" if isinstance(carbs, (int, float)) else str(carbs)
    fat_str = f"{fat:g}" if isinstance(fat, (int, float)) else str(fat)
    return (
        f'<div class="macro-chips-row">'
        f'<div class="macro-chip"><span class="macro-chip-dot protein"></span><span class="macro-chip-lbl">Protein</span><span class="macro-chip-val">{prot_str}g</span></div>'
        f'<div class="macro-chip"><span class="macro-chip-dot carbs"></span><span class="macro-chip-lbl">Carbs</span><span class="macro-chip-val">{carb_str}g</span></div>'
        f'<div class="macro-chip"><span class="macro-chip-dot fat"></span><span class="macro-chip-lbl">Fat</span><span class="macro-chip-val">{fat_str}g</span></div>'
        f'</div>'
    )

def render_targets_card(calorie_target: float, protein: float, carbs: float, fat: float):
    chips_html = render_macro_chips(protein, carbs, fat)
    cal_str = f"{calorie_target:g}" if isinstance(calorie_target, (int, float)) else str(calorie_target)
    st.markdown(
        f'<div class="tracker-card">'
        f'<div class="tracker-card-header"><span class="tracker-card-title">Daily Nutrition Targets</span></div>'
        f'<div class="tracker-cal-row"><div class="tracker-cal-val">{cal_str} <span>kcal</span></div><div class="tracker-cal-sub">Daily Baseline Goal</div></div>'
        f'{chips_html}'
        f'</div>',
        unsafe_allow_html=True
    )

def render_meal_result_card(dish_name: str, confidence: float, verdict: str, 
                            meal_calories: float, target_calories: float,
                            protein: float, carbs: float, fat: float):
    verdict_class = "verdict-fits" if "Fits" in str(verdict) else "verdict-mod"
    verdict_symbol = "Fits your target" if "Fits" in str(verdict) else "Suggested portion adjustment"
    
    cal_consumed = float(meal_calories or 0)
    cal_budget = float(target_calories or 1)
    ratio_pct = min(max(int((cal_consumed / cal_budget) * 100), 5), 100) if cal_budget > 0 else 100
    
    chips_html = render_macro_chips(protein, carbs, fat)
    
    st.markdown(
        f'<div class="tracker-card">'
        f'<div class="tracker-card-header">'
        f'<span class="tracker-card-title">{dish_name.title()}</span>'
        f'<span class="verdict-badge {verdict_class}">{verdict_symbol}</span>'
        f'</div>'
        f'<div class="tracker-cal-row">'
        f'<div class="tracker-cal-val">{cal_consumed:g} <span>/ {cal_budget:g} kcal</span></div>'
        f'<div class="tracker-cal-sub">{ratio_pct}% of meal budget</div>'
        f'</div>'
        f'<div class="tracker-progress-track">'
        f'<div class="tracker-progress-fill" style="width: {ratio_pct}%;"></div>'
        f'</div>'
        f'{chips_html}'
        f'<div class="tracker-card-footer">USDA Reference Data • {confidence:.0%} identification match</div>'
        f'</div>',
        unsafe_allow_html=True
    )

def render_skeleton_state():
    """Renders quiet loading placeholders while meal analysis processes."""
    st.markdown("""
        <div class="quiet-loader">
            <div class="loader-title">Analyzing your meal...</div>
            <div class="loader-sub">Identifying ingredients and calculating nutritional breakdown</div>
            <div class="loader-pulse-bar"></div>
        </div>
        <div class="data-card">
            <div class="skeleton-box skeleton-text-lg"></div>
            <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.75rem; margin-bottom: 1rem;">
                <div class="skeleton-box skeleton-card"></div>
                <div class="skeleton-box skeleton-card"></div>
                <div class="skeleton-box skeleton-card"></div>
                <div class="skeleton-box skeleton-card"></div>
            </div>
            <div class="skeleton-box skeleton-block"></div>
            <div class="skeleton-box skeleton-block"></div>
        </div>
    """, unsafe_allow_html=True)

def clean_recipe_text(text: str) -> str:
    """Cleans and sanitizes recipe markdown text to prevent unclosed headers, massive scaling, or script/HTML injection."""
    if not text:
        return ""
    text = text.strip()
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        stripped_line = line.strip()
        # Escape any raw HTML tags in the line while preserving markdown formatting
        safe_line = stripped_line.replace("<", "&lt;").replace(">", "&gt;")
        if safe_line.startswith("#"):
            content = safe_line.lstrip("#").strip()
            cleaned_lines.append(f"**{content}**")
        else:
            cleaned_lines.append(safe_line)
    return "\n".join(cleaned_lines)

# Initialize Session States
for key, val in [("oauth_session", None), ("profile", None), ("editing_profile", False),
                 ("awaiting_confirmation", False), ("detected_dish_name", ""), ("is_not_food", False), ("analysis_results", None)]:
    if key not in st.session_state:
        st.session_state[key] = val

# Inspect Active Authentication & Enforce Session Security Lifecycle
is_authenticated = False
user_email = None
user_display_name = "Athlete"
user_avatar = None
session_expired_notice = None

# Native Streamlit Google OAuth (evaluated on every page render)
if hasattr(st, "user") and st.user and getattr(st.user, "is_logged_in", False):
    current_email = getattr(st.user, "email", None)
    current_name = getattr(st.user, "name", None) or (current_email.split("@")[0] if current_email else "Athlete")
    current_picture = getattr(st.user, "picture", None)
    
    # Active Session Timeout Enforcement (Inactivity: 30m, Absolute: 24h) evaluated on EVERY render
    oauth_sess = st.session_state.get("oauth_session")
    if not oauth_sess or oauth_sess.get("email") != current_email:
        # Fresh Google OAuth login: establish session tracking
        st.session_state.oauth_session = create_session(current_email, current_name)
        log_security_event(
            EVENT_AUTH_LOGIN_SUCCESS,
            severity="INFO",
            actor=current_email,
            action_taken="ALLOW",
            resource="google_oauth",
            details={"provider": "google"}
        )
        is_authenticated = True
        user_email = current_email
        user_display_name = current_name
        user_avatar = current_picture
    else:
        # Existing session: validate inactivity & absolute duration
        is_valid, reason = validate_session(oauth_sess)
        if not is_valid:
            # Session expired (idle > 30m or total > 24h)
            st.session_state.oauth_session = None
            st.session_state.profile = None
            st.session_state.editing_profile = False
            session_expired_notice = reason
            log_security_event(
                EVENT_AUTH_LOCKOUT,
                severity="WARNING",
                actor=current_email,
                action_taken="LOGOUT_TIMEOUT",
                resource="session_lifecycle",
                details={"reason": reason}
            )
            if hasattr(st, "logout"):
                try:
                    st.logout()
                except Exception:
                    pass
            is_authenticated = False
        else:
            touch_session(oauth_sess)
            is_authenticated = True
            user_email = current_email
            user_display_name = current_name
            user_avatar = current_picture

# --- 1. ZERO-TRUST AUTHENTICATION GATE (GOOGLE OAUTH 2.0) ---
if not is_authenticated:
    st.markdown("""
        <div class="auth-container">
            <div class="auth-badge">Personalized Nutrition</div>
            <div class="auth-title">Welcome to DietFit</div>
            <div class="auth-desc">
                Snap a photo of your meal to get instant nutrition insights, check alignment
                with your daily macro targets, and receive personalized recipe adjustments.
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    col_a, col_b, col_c = st.columns([1, 2, 1])
    with col_b:
        if session_expired_notice:
            st.markdown(f"""
                <div class="security-banner warning" style="margin-bottom: 1.5rem;">
                    <span>Session Terminated: {session_expired_notice}</span>
                </div>
            """, unsafe_allow_html=True)
            
        st.markdown("""
            <div style="background: #1C221E; border: 1px solid #2B352E; border-radius: 12px; padding: 2rem; text-align: center; box-shadow: 0 8px 24px rgba(0,0,0,0.3); margin-bottom: 1.5rem;">
                <div style="font-size: 1.2rem; font-weight: 600; color: #F4EFE6; margin-bottom: 0.5rem;">Google Sign-In</div>
                <div style="font-size: 0.88rem; color: #98A39A; line-height: 1.5; margin-bottom: 1.5rem;">
                    Sign in with your Google account to access your customized nutrition profile and meal analysis.
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        if st.button("Sign in with Google", key="btn_google_login", type="primary", use_container_width=True):
            try:
                if hasattr(st, "login"):
                    st.login("google")
                else:
                    st.error("Streamlit native login feature (st.login) is not available.")
            except Exception as e:
                st.error(f"Google OAuth initialization error: {e}")

    st.stop()

# --- 2. AUTHENTICATED USER DASHBOARD ---

# Sync user info with storage & auto-provision new Google users
if is_authenticated and user_email:
    rec = get_user_record(user_email, authenticated_email=user_email)
    if not rec:
        create_user_record(email=user_email, name=user_display_name)
        st.session_state.profile = "NEW"
    elif not st.session_state.profile:
        try:
            profile = load_user(user_email, authenticated_email=user_email)
            st.session_state.profile = profile if profile else "NEW"
        except ResourceOwnershipError as e:
            st.error(f"Security Access Violation: {e}")
            st.stop()

# Top Brand & User Header Bar
col_h1, col_h2 = st.columns([3, 1.2])
with col_h1:
    st.markdown(f"""
        <div class="brand-title">
            <span class="brand-icon">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z"/>
                    <path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12"/>
                </svg>
            </span>
            DietFit
        </div>
        <div class="brand-subtitle">Personalized Nutrition & Meal Intelligence</div>
    """, unsafe_allow_html=True)
with col_h2:
    if user_avatar:
        st.markdown(f"""
            <div style="display: flex; align-items: center; justify-content: flex-end; gap: 0.75rem; padding-top: 0.2rem;">
                <img src="{user_avatar}" class="user-avatar-badge" alt="Avatar" />
                <div>
                    <div style="font-size: 0.88rem; font-weight: 600; color: #F4EFE6;">{user_display_name}</div>
                    <div style="font-size: 0.75rem; color: #98A39A;">{user_email}</div>
                </div>
            </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
            <div style="text-align: right; padding-top: 0.5rem;">
                <div style="font-size: 0.88rem; font-weight: 600; color: #F4EFE6;">{user_display_name}</div>
                <div style="font-size: 0.75rem; color: #98A39A;">{user_email}</div>
            </div>
        """, unsafe_allow_html=True)
        
    if st.button("Sign Out", key="top_logout", use_container_width=True):
        st.session_state.oauth_session = None
        st.session_state.profile = None
        st.session_state.editing_profile = False
        st.session_state.awaiting_confirmation = False
        st.session_state.detected_dish_name = ""
        st.session_state.is_not_food = False
        st.session_state.analysis_results = None
        if hasattr(st, "logout"):
            try:
                st.logout()
            except Exception:
                pass
        st.rerun()

st.markdown("<hr style='border-color: #2B352E; margin-top: 0.5rem; margin-bottom: 1.5rem;'>", unsafe_allow_html=True)

# Sidebar Profile Controls
with st.sidebar:
    st.markdown("### Your Profile")
    st.markdown(f"""
        <div class="user-sidebar-box">
            <div class="user-sidebar-name">{user_display_name}</div>
            <div class="user-sidebar-email">{user_email}</div>
        </div>
    """, unsafe_allow_html=True)
    
    prof = st.session_state.profile
    if isinstance(prof, dict):
        st.markdown(f"**Goal:** {prof.get('goal', '').replace('_', ' ').title()}")
        st.markdown(f"**Diet:** {prof.get('diet_type', '').title()}")
        st.markdown(f"**Weight:** {prof.get('weight_kg')} kg | **Height:** {prof.get('height_cm')} cm")
        st.markdown(f"**Daily Calories:** {prof.get('calorie_target')} kcal")
        
        if st.button("Edit Profile", key="btn_edit_profile", use_container_width=True):
            st.session_state.editing_profile = not st.session_state.editing_profile
            st.rerun()
        
    if st.button("Sign Out", key="sidebar_logout", use_container_width=True):
        st.session_state.oauth_session = None
        st.session_state.profile = None
        st.session_state.editing_profile = False
        st.session_state.awaiting_confirmation = False
        st.session_state.detected_dish_name = ""
        st.session_state.is_not_food = False
        st.session_state.analysis_results = None
        if hasattr(st, "logout"):
            try:
                st.logout()
            except Exception:
                pass
        st.rerun()


# First Time Setup / Registration Form
if st.session_state.profile == "NEW":
    st.markdown("### Set Up Your Nutrition Profile")
    st.markdown("Calculate your daily baseline calories and macronutrient split based on your metabolic profile.")
    
    with st.form("registration_form"):
        c1, c2 = st.columns(2)
        with c1:
            gender = st.selectbox("Gender", ["Male", "Female"])
            age = st.number_input("Age (years)", min_value=1, max_value=120, value=25)
            height = st.number_input("Height (cm)", min_value=50.0, max_value=250.0, value=175.0)
            weight = st.number_input("Weight (kg)", min_value=10.0, max_value=300.0, value=70.0)
        with c2:
            activity = st.selectbox("Activity Level", ["Sedentary", "Lightly Active", "Moderately Active", "Very Active", "Extra Active"])
            goal = st.selectbox("Fitness Goal", ["Lose Fat", "Build Muscle", "Maintain"])
            diet = st.selectbox("Diet Type", ["Balanced", "Vegan", "Keto", "Low Carb"])
        
        submit_reg = st.form_submit_button("Save Profile & Calculate Targets")
        
    if submit_reg:
        try:
            validated_inputs = validate_profile_inputs(
                weight=weight,
                height=height,
                age=age,
                gender=gender,
                activity=activity,
                goal=goal,
                diet=diet
            )
        except ValidationError as ve:
            st.error(f"Invalid profile parameters: {ve}")
            st.stop()
            
        placeholder = st.empty()
        with placeholder.container():
            render_skeleton_state()
            input_state = {
                "status": "calibrate",
                **validated_inputs
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
            save_user(user_email, new_profile, authenticated_email=user_email)
            st.session_state.profile = new_profile
            st.rerun()

elif st.session_state.editing_profile:
    st.markdown("### Edit Nutrition Profile")
    st.markdown("Update your personal parameters to recalculate your baseline targets.")
    
    prof = st.session_state.profile if isinstance(st.session_state.profile, dict) else {}
    
    genders = ["Male", "Female"]
    curr_gender = str(prof.get("gender", "male")).strip().capitalize()
    gender_idx = genders.index(curr_gender) if curr_gender in genders else 0
    
    activities = ["Sedentary", "Lightly Active", "Moderately Active", "Very Active", "Extra Active"]
    curr_activity = str(prof.get("activity_level", "sedentary")).replace("_", " ").strip().title()
    activity_idx = activities.index(curr_activity) if curr_activity in activities else 0
    
    goals = ["Lose Fat", "Build Muscle", "Maintain"]
    curr_goal = str(prof.get("goal", "maintain")).replace("_", " ").strip().title()
    goal_idx = goals.index(curr_goal) if curr_goal in goals else 2
    
    diets = ["Balanced", "Vegan", "Keto", "Low Carb"]
    curr_diet = str(prof.get("diet_type", "balanced")).replace("_", " ").strip().title()
    diet_idx = diets.index(curr_diet) if curr_diet in diets else 0
    
    with st.form("edit_profile_form"):
        c1, c2 = st.columns(2)
        with c1:
            gender = st.selectbox("Gender", genders, index=gender_idx)
            age = st.number_input("Age (years)", min_value=1, max_value=120, value=int(prof.get("age", 25)))
            height = st.number_input("Height (cm)", min_value=50.0, max_value=250.0, value=float(prof.get("height_cm", 175.0)))
            weight = st.number_input("Weight (kg)", min_value=10.0, max_value=300.0, value=float(prof.get("weight_kg", 70.0)))
        with c2:
            activity = st.selectbox("Activity Level", activities, index=activity_idx)
            goal = st.selectbox("Fitness Goal", goals, index=goal_idx)
            diet = st.selectbox("Diet Type", diets, index=diet_idx)
        
        submit_edit = st.form_submit_button("Save Changes")
        
    if submit_edit:
        try:
            validated_inputs = validate_profile_inputs(
                weight=weight,
                height=height,
                age=age,
                gender=gender,
                activity=activity,
                goal=goal,
                diet=diet
            )
        except ValidationError as ve:
            st.error(f"Invalid profile parameters: {ve}")
            st.stop()
            
        placeholder = st.empty()
        with placeholder.container():
            render_skeleton_state()
            input_state = {
                "status": "calibrate",
                **validated_inputs
            }
            output_state = app_graph.invoke(input_state)
            updated_profile = {
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
            save_user(user_email, updated_profile, authenticated_email=user_email)
            st.session_state.profile = updated_profile
            st.session_state.editing_profile = False
            st.rerun()

else:
    prof = st.session_state.profile
    # Auto-calibrate if required keys missing
    if not all(prof.get(k) for k in ["calorie_target", "protein_target", "carb_target", "fat_target"]):
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
        save_user(user_email, calibrated_prof, authenticated_email=user_email)
        st.session_state.profile = calibrated_prof
        st.rerun()

    # MASTER-DETAIL TWO-COLUMN LAYOUT
    col_left, col_right = st.columns([1.1, 1.9])

    # --- LEFT COLUMN: NUTRITION TARGETS & MEAL PHOTO UPLOAD ---
    with col_left:
        # 1. Unified Nutrition Targets Card
        render_targets_card(
            calorie_target=prof.get("calorie_target", 2000.0),
            protein=prof.get("protein_target", 150.0),
            carbs=prof.get("carb_target", 200.0),
            fat=prof.get("fat_target", 70.0)
        )
        
        # Meal Budget Adjustment slider
        daily_cal_target = float(prof.get("calorie_target", 2000.0))
        meal_calorie_budget = st.slider(
            "Meal Target Scale (kcal)", 
            min_value=100.0, 
            max_value=daily_cal_target, 
            value=daily_cal_target, 
            step=50.0,
            help="Adjust the calorie target proportion for this specific meal."
        )
        scale = meal_calorie_budget / daily_cal_target if daily_cal_target > 0 else 1.0
        
        custom_prof = prof.copy()
        custom_prof.update({
            "calorie_target": meal_calorie_budget,
            "protein_target": round(float(prof.get("protein_target", 150.0)) * scale, 1),
            "carb_target": round(float(prof.get("carb_target", 200.0)) * scale, 1),
            "fat_target": round(float(prof.get("fat_target", 70.0)) * scale, 1)
        })

        st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)

        # 2. Photo Uploader Dropzone
        st.markdown("""
            <div class="media-upload-card">
                <div class="media-upload-title">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
                        <circle cx="12" cy="13" r="4"/>
                    </svg>
                    Upload Meal Photo
                </div>
                <div class="media-upload-desc">Select or capture a plate photo from your device</div>
            </div>
        """, unsafe_allow_html=True)
        uploaded_file = st.file_uploader("Select meal image", type=["jpg", "jpeg", "png", "webp"], label_visibility="collapsed")
        
        valid_image_obj = None
        if uploaded_file:
            is_valid_img, img_msg, valid_image_obj = validate_uploaded_image(uploaded_file)
            if not is_valid_img:
                st.error(f"Unsafe or Invalid File Upload: {img_msg}")
            else:
                st.image(valid_image_obj, caption="Meal Preview", use_container_width=True)

    # --- RIGHT COLUMN: QUIET LOADER, EMPTY WORKSPACE & NUTRITION RESULTS ---
    with col_right:
        # Action Handler for Processing Analysis
        def run_full_pipeline(dish_name_override=None, image_file=None):
            # Enforce AI Generation rate limiting per user/session
            user_ident = user_email or "anonymous_session"
            allowed_ai, cooldown_ai = check_abuse_limit("ai_generation", user_ident)
            if not allowed_ai:
                log_security_event(
                    EVENT_ABUSE_THROTTLED,
                    severity="WARNING",
                    actor=user_ident,
                    action_taken="THROTTLE",
                    resource="ai_pipeline_execution",
                    details={"cooldown": cooldown_ai}
                )
                st.error(f"Rate Limit: Generation burst limit reached. Please wait {cooldown_ai} seconds before trying again.")
                return
            record_abuse_call("ai_generation", user_ident)

            results_container = st.empty()
            with results_container.container():
                # Render Quiet Skeleton Loading State while running pipeline
                render_skeleton_state()
                
                clean_dish_override = None
                if dish_name_override:
                    try:
                        clean_dish_override = validate_dish_name(dish_name_override)
                    except ValidationError as ve:
                        st.error(f"Invalid dish name: {ve}")
                        return
                
                input_state = {
                    "status": "analyze",
                    "email": user_email,
                    "goal": custom_prof.get("goal"),
                    "diet_type": custom_prof.get("diet_type"),
                    "calorie_target": custom_prof.get("calorie_target"),
                    "protein_target": custom_prof.get("protein_target"),
                    "carb_target": custom_prof.get("carb_target"),
                    "fat_target": custom_prof.get("fat_target"),
                }
                if image_file:
                    input_state["image_path"] = image_file
                if clean_dish_override:
                    input_state["dish_name"] = clean_dish_override

                try:
                    res_state = app_graph.invoke(input_state)
                except RateLimitExceeded as rle:
                    log_security_event(
                        EVENT_ABUSE_THROTTLED,
                        severity="WARNING",
                        actor=user_ident,
                        action_taken="THROTTLE",
                        resource="ai_subagent_pipeline",
                        details={"error": str(rle)}
                    )
                    st.error(f"Request Throttled: {rle}")
                    return
                
                is_food = res_state.get("is_food", True)
                conf = res_state.get("vision_confidence", 1.0)
                dish_name = res_state.get("dish_name", "Identified Dish")
                st.session_state.detected_dish_name = dish_name or ""
                
                if not clean_dish_override:
                    if not is_food:
                        st.session_state.awaiting_confirmation = True
                        st.session_state.is_not_food = True
                        st.session_state.analysis_results = None
                    elif conf < 0.70:
                        st.session_state.awaiting_confirmation = True
                        st.session_state.is_not_food = False
                        st.session_state.analysis_results = None
                    else:
                        st.session_state.awaiting_confirmation = False
                        st.session_state.is_not_food = False
                        st.session_state.analysis_results = {
                            "dish_name": dish_name,
                            "confidence": conf,
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
                else:
                    st.session_state.awaiting_confirmation = False
                    st.session_state.is_not_food = False
                    st.session_state.analysis_results = {
                        "dish_name": dish_name,
                        "confidence": conf,
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

        # Trigger Buttons
        if uploaded_file and valid_image_obj and not st.session_state.analysis_results and not st.session_state.awaiting_confirmation:
            if st.button("Analyze Meal", type="primary", use_container_width=True):
                run_full_pipeline(image_file=uploaded_file)

        # Quiet Empty Workspace when idle
        if not st.session_state.analysis_results and not st.session_state.awaiting_confirmation:
            st.markdown("""
                <div class="empty-workspace">
                    <div class="empty-plate-icon">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                            <circle cx="12" cy="12" r="9"/>
                            <circle cx="12" cy="12" r="5"/>
                            <line x1="12" y1="3" x2="12" y2="7"/>
                        </svg>
                    </div>
                    <div class="empty-title">Ready for Meal Analysis</div>
                    <div class="empty-text">
                        Upload a photo of your meal on the left to see its estimated nutritional breakdown, target fit, and tailored recipe adjustments.
                    </div>
                </div>
            """, unsafe_allow_html=True)

        # Low Confidence / Non-Food Confirmation Box
        if st.session_state.awaiting_confirmation:
            if st.session_state.get("is_not_food", False):
                st.warning("This doesn't look like a food photo. Please upload a clear photo of your meal, or type the dish name below so I can look it up directly.")
                confirmed_name = st.text_input("Dish Name", placeholder="e.g., Grilled Chicken Salad")
                if st.button("Look Up Dish & Analyze", type="primary", use_container_width=True):
                    if confirmed_name.strip():
                        run_full_pipeline(dish_name_override=confirmed_name.strip())
                    else:
                        st.error("Please enter a valid dish name.")
            else:
                st.warning(f"We couldn't identify this dish with high confidence ('{st.session_state.detected_dish_name}'). Please confirm or edit the dish name below.")
                confirmed_name = st.text_input("Dish Name", value=st.session_state.detected_dish_name)
                if st.button("Confirm Dish Name & Analyze", type="primary", use_container_width=True):
                    if confirmed_name.strip():
                        run_full_pipeline(dish_name_override=confirmed_name.strip())
                    else:
                        st.error("Please enter a valid dish name.")

        # Display Pipeline Analysis Results
        if st.session_state.analysis_results:
            res = st.session_state.analysis_results
            dish_name = res.get("dish_name", "Identified Dish")
            conf = res.get("confidence", 1.0)
            verdict = res["advice"].get("verdict", "Fits Target")
            macros = res.get("macros", {})

            # Render Unified Meal Result Card
            render_meal_result_card(
                dish_name=dish_name,
                confidence=conf,
                verdict=verdict,
                meal_calories=macros.get("calories", 0),
                target_calories=custom_prof.get("calorie_target", 650.0),
                protein=macros.get("protein", 0),
                carbs=macros.get("carbs", 0),
                fat=macros.get("fat", 0)
            )

            # Recipe & Advisor Explanation Breakdown
            st.markdown("<div class='section-title'>Recipe & Recommendations</div>", unsafe_allow_html=True)

            tab1, tab2, tab3 = st.tabs(["Personalized Recipe", "Original Recipe", "Nutritional Advice"])
            
            with tab1:
                st.markdown(clean_recipe_text(res["advice"].get("adjusted_recipe", "No adjusted content.")))
                
            with tab2:
                st.markdown(clean_recipe_text(res["recipe_info"].get("original_recipe", "No original recipe.")))
                if res["recipe_info"].get("recipe_source_url"):
                    st.markdown(f"[Source Document Link]({res['recipe_info'].get('recipe_source_url')})")
                
            with tab3:
                st.markdown(clean_recipe_text(res["advice"].get("explanation", "")))

            if st.button("Analyze Another Meal", use_container_width=True):
                st.session_state.analysis_results = None
                st.session_state.awaiting_confirmation = False
                st.session_state.is_not_food = False
                st.rerun()
