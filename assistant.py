
import datetime
import os
import sys
import joblib
import subprocess
import webbrowser
import threading
import speech_recognition as sr
import pyttsx3
from urllib.parse import quote_plus

# Optional imports with graceful fallbacks
try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

try:
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    PYCAW_AVAILABLE = True
except ImportError:
    PYCAW_AVAILABLE = False

try:
    from google import genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# Load .env file (must come before reading any config values)
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False


# -----------------------------
# Configuration  (all values read from .env / environment)
# -----------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "models", "voice_intant_model.joblib")
SCREENSHOT_DIR = os.path.join(os.path.expanduser("~"), "Pictures", "VoiceAssistant")

# Language: en-IN | ta-IN | en-US  (set in .env or environment)
RECOGNITION_LANGUAGE = os.environ.get("RECOGNITION_LANGUAGE", "en-IN")

# Gemini API key — loaded from .env, never hardcoded
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

# Confidence threshold for ML model
CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.3"))

# Max recognition retries on failure
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "2"))


# -----------------------------
# Load trained model
# -----------------------------

model = joblib.load(MODEL_PATH)


# -----------------------------
# Initialize TTS engine
# -----------------------------

engine = pyttsx3.init()
engine.setProperty("rate", 160)       # Speaking speed
engine.setProperty("volume", 1.0)     # Volume (0.0 to 1.0)

# Try to set a natural-sounding voice
voices = engine.getProperty("voices")
for voice in voices:
    if "zira" in voice.name.lower() or "hazel" in voice.name.lower():
        engine.setProperty("voice", voice.id)
        break


# -----------------------------
# Initialize Gemini AI (optional)
# -----------------------------

gemini_model = None

# API Key validation check
is_placeholder_key = GEMINI_API_KEY.lower() in ["", "your_gemini_api_key_here", "none"]

if GEMINI_AVAILABLE and not is_placeholder_key:
    try:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        gemini_model = "gemini-3.5-flash-lite"
        masked_key = GEMINI_API_KEY[:4] + "..." + GEMINI_API_KEY[-4:] if len(GEMINI_API_KEY) > 8 else "***"
        print(f"✅ Gemini AI connected. (Key: {masked_key})")
    except Exception as e:
        gemini_client = None
        print(f"⚠️  Gemini AI connection failed: {e}")
else:
    gemini_client = None
    if is_placeholder_key:
        print("🔒 Security Notice: GEMINI_API_KEY not configured or using default placeholder in .env")
        print("   Add your actual key to d:\\VoiceAssistant\\.env to activate Gemini AI features.")


# -----------------------------
# Initialize speech recognizer
# -----------------------------

recognizer = sr.Recognizer()
recognizer.dynamic_energy_threshold = True
recognizer.energy_threshold = 300
recognizer.pause_threshold = 0.9
recognizer.non_speaking_duration = 0.4
recognizer.phrase_threshold = 0.3


# -----------------------------
# Text-to-speech
# -----------------------------

def speak(text):
    print(f"🤖 Assistant: {text}")
    try:
        engine.say(text)
        engine.runAndWait()
    except Exception as e:
        print(f"⚠️  TTS error: {e}")


# -----------------------------
# Microphone calibration
# (improved with longer warm-up and noise profiling)
# -----------------------------

def calibrate_microphone():
    print("\n🎙️  Calibrating microphone for ambient noise...")
    try:
        with sr.Microphone() as source:
            # Phase 1: short initial calibration
            recognizer.adjust_for_ambient_noise(source, duration=1)
            print(f"   Initial threshold: {recognizer.energy_threshold:.1f}")

            # Phase 2: refined calibration
            recognizer.adjust_for_ambient_noise(source, duration=2)
            print(f"   Refined threshold: {recognizer.energy_threshold:.1f}")

        print("✅ Microphone ready.\n")
        return True

    except OSError as e:
        print(f"❌ Microphone error: {e}")
        return False


# -----------------------------
# Language selection
# -----------------------------

def select_language():
    global RECOGNITION_LANGUAGE
    print("\n🌐 Language Selection:")
    print("   1. English (India) [en-IN]")
    print("   2. Tamil (India)   [ta-IN]")
    print("   3. English (US)    [en-US]")

    choice = input("   Choose (1/2/3) [default=1]: ").strip()

    if choice == "2":
        RECOGNITION_LANGUAGE = "ta-IN"
        speak("Tamil language selected. நான் தமிழ் புரிந்துகொள்கிறேன்.")
    elif choice == "3":
        RECOGNITION_LANGUAGE = "en-US"
        speak("American English selected.")
    else:
        RECOGNITION_LANGUAGE = "en-IN"
        speak("English India language selected.")

    print(f"✅ Recognition language: {RECOGNITION_LANGUAGE}\n")


# -----------------------------
# Speech recognition
# (with retry, noise handling, bilingual support)
# -----------------------------

def listen(retries=MAX_RETRIES):
    for attempt in range(1, retries + 2):
        try:
            with sr.Microphone() as source:
                # Recalibrate briefly on each listen for noise adaptation
                recognizer.adjust_for_ambient_noise(source, duration=0.3)
                print("🎧 Listening... Speak clearly.")

                audio = recognizer.listen(
                    source,
                    timeout=10,
                    phrase_time_limit=8
                )

            # Try primary language
            try:
                text = recognizer.recognize_google(
                    audio,
                    language=RECOGNITION_LANGUAGE
                ).strip().lower()

                if text:
                    print(f"👤 You said: {text}")
                    return text

            except sr.UnknownValueError:
                # Fallback: try English if primary was Tamil
                if RECOGNITION_LANGUAGE == "ta-IN":
                    try:
                        text = recognizer.recognize_google(
                            audio,
                            language="en-IN"
                        ).strip().lower()
                        if text:
                            print(f"👤 You said (en fallback): {text}")
                            return text
                    except Exception:
                        pass

                if attempt <= retries:
                    print(f"🔄 Could not understand. Retry {attempt}/{retries}...")
                else:
                    print("❌ Could not recognize speech. Please try again.")

        except sr.WaitTimeoutError:
            print("⏱️  No speech detected (timeout).")
            return ""

        except sr.RequestError as e:
            print(f"🌐 Google Speech API error: {e}")
            return ""

        except OSError as e:
            print(f"❌ Microphone error: {e}")
            return ""

        except Exception as e:
            print(f"⚠️  Unexpected error: {e}")
            return ""

    return ""


# -----------------------------
# Intent classification
# (expanded, confidence-aware)
# -----------------------------

def identify_intent(text):
    text = text.lower().strip()

    # --- Direct exit commands ---
    exit_commands = {
        "goodbye", "good bye", "bye", "bye assistant", "goodbye assistant",
        "exit", "quit", "stop", "stop assistant", "close assistant",
        "close the assistant", "see you later", "shut down", "that's all",
        "i'm done", "exit the assistant",
        "வெளியேறு", "முடிந்தது", "பை", "குட்பை", "நன்றி"
    }
    if text in exit_commands:
        return "exit"

    # --- Greeting commands ---
    greetings = {
        "hello", "hi", "hey", "hi there", "hey assistant", "hello assistant",
        "good morning", "good afternoon", "good evening", "howdy",
        "greetings", "what's up", "namaste", "vanakkam", "hey there",
        "வணக்கம்", "ஹலோ", "வணக்கம் அசிஸ்டன்ட்", "காலை வணக்கம்", "மதிய வணக்கம்", "மாலை வணக்கம்"
    }
    if text in greetings:
        return "greeting"

    # --- Time ---
    time_keywords = ["time", "clock", "hour", "what time", "மணி என்ன", "நேரம் என்ன", "நேரம்", "மணி"]
    if any(k in text for k in time_keywords):
        return "get_time"

    # --- Date ---
    date_keywords = ["date", "today's date", "what day", "what is today", "தேதி", "நாள்", "இன்றைய தேதி"]
    if any(k in text for k in date_keywords):
        return "get_date"

    # --- YouTube ---
    if "youtube" in text or "யூடியூப்" in text:
        return "open_youtube"

    # --- Tutorial / Learning / Searches ---
    if "tutorial" in text or "course" in text:
        return "web_search"

    # --- Volume controls ---
    vol_up_triggers = ["louder", "volume up", "increase volume", "turn up", "raise volume", "higher volume", "raise the volume", "வால்யூம் கூட்டு", "சத்தத்தை கூட்டு", "கூட்டு"]
    if any(w in text for w in vol_up_triggers):
        return "volume_up"

    vol_down_triggers = ["quieter", "volume down", "decrease volume", "turn down", "lower volume", "reduce volume", "decrease the volume", "வால்யூம் குறை", "சத்தத்தை குறை", "குறை"]
    if any(w in text for w in vol_down_triggers):
        return "volume_down"

    vol_mute_triggers = ["mute", "turn off sound", "no sound", "silence please", "true off sound", "மியூட்", "சத்தம் வேண்டாம்"]
    if any(w in text for w in vol_mute_triggers) and "un" not in text:
        return "volume_mute"

    vol_unmute_triggers = ["unmute", "turn on sound", "enable sound", "restore sound", "true on sound", "அன்மியூட்"]
    if any(w in text for w in vol_unmute_triggers):
        return "volume_unmute"

    if text.strip() in ["volume", "வால்யூம்"]:
        return "volume_up"

    # --- Screenshot ---
    if any(w in text for w in ["screenshot", "screen capture", "capture screen", "snap the screen", "ஸ்கிரீன்ஷாட்"]):
        return "screenshot"

    # --- Open folder ---
    folder_triggers = ["downloads folder", "documents folder", "desktop folder", "picture folder", "pictures folder",
                       "my downloads", "my documents", "pictures folder", "my pictures",
                       "open my files", "show downloads", "navigate to", "கோப்பு", "போல்டர்"]
    if any(t in text for t in folder_triggers):
        return "open_folder"

    # --- Open app ---
    app_triggers = ["open chrome", "launch chrome", "open google chrome",
                    "open notepad", "launch notepad", "open calculator",
                    "launch calculator", "open paint", "open file explorer",
                    "open explorer", "open vs code", "launch vs code",
                    "open visual studio", "open task manager", "open word",
                    "open excel", "open powerpoint", "open an application",
                    "run notepad", "start calculator", "திற", "ஓபன்"]
    if any(t in text for t in app_triggers):
        return "open_app"

    # --- Summarize ---
    if any(w in text for w in ["summarize", "summary", "make it shorter", "tldr",
                                "shorten this", "condense", "brief me", "highlights", "சுருக்கம்", "சுருக்கு"]):
        return "summarize"

    # --- Web search (prefix-based) ---
    search_prefixes = [
        "search for ", "search ", "find ", "look up ",
        "lookup ", "can you search for ", "please search ", "please find ",
        "தேடு ", "கூகுளில் தேடு "
    ]
    if any(text.startswith(p) for p in search_prefixes) or "தேடு" in text:
        return "web_search"

    # --- AI questions ---
    ai_triggers = ["what is", "what are", "explain ", "how does", "how do",
                   "tell me about", "who is", "why is", "why are",
                   "give me information", "can you help me understand",
                   "what do you know about", "என்றால் என்ன", "பற்றி சொல்", "விளக்கு", "எப்படி"]
    if any(text.startswith(t) or t in text for t in ai_triggers):
        return "ask_ai"

    # --- ML model prediction fallback ---
    try:
        scores = model.decision_function([text])[0]
        classes = model.classes_
        best_index = scores.argmax()
        confidence = float(scores[best_index])

        print(f"🧠 ML confidence: {round(confidence, 2)} → {classes[best_index]}")

        if confidence >= CONFIDENCE_THRESHOLD:
            return classes[best_index]

    except Exception as e:
        print(f"⚠️  Model error: {e}")

    return "unknown"


# -----------------------------
# Volume control (Windows)
# -----------------------------

def get_volume_interface():
    if not PYCAW_AVAILABLE:
        return None
    try:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(interface, POINTER(IAudioEndpointVolume))
    except Exception:
        return None


def change_volume(action):
    vol = get_volume_interface()

    if vol:
        try:
            current = vol.GetMasterVolumeLevelScalar()
            if action == "up":
                new_vol = min(1.0, current + 0.1)
                vol.SetMasterVolumeLevelScalar(new_vol, None)
                speak(f"Volume increased to {int(new_vol * 100)} percent.")
            elif action == "down":
                new_vol = max(0.0, current - 0.1)
                vol.SetMasterVolumeLevelScalar(new_vol, None)
                speak(f"Volume decreased to {int(new_vol * 100)} percent.")
            elif action == "mute":
                vol.SetMute(1, None)
                speak("Volume muted.")
            elif action == "unmute":
                vol.SetMute(0, None)
                speak("Volume unmuted.")
            return
        except Exception as e:
            print(f"⚠️  pycaw error: {e}")

    # Fallback: Windows keyboard simulation
    try:
        import ctypes
        if action == "up":
            for _ in range(5):
                ctypes.windll.user32.keybd_event(0xAF, 0, 0, 0)
                ctypes.windll.user32.keybd_event(0xAF, 0, 2, 0)
            speak("Volume increased.")
        elif action == "down":
            for _ in range(5):
                ctypes.windll.user32.keybd_event(0xAE, 0, 0, 0)
                ctypes.windll.user32.keybd_event(0xAE, 0, 2, 0)
            speak("Volume decreased.")
        elif action == "mute":
            ctypes.windll.user32.keybd_event(0xAD, 0, 0, 0)
            ctypes.windll.user32.keybd_event(0xAD, 0, 2, 0)
            speak("Toggled mute.")
        elif action == "unmute":
            ctypes.windll.user32.keybd_event(0xAD, 0, 0, 0)
            ctypes.windll.user32.keybd_event(0xAD, 0, 2, 0)
            speak("Toggled mute.")
    except Exception as e:
        speak("Sorry, I could not control the volume.")
        print(f"⚠️  Volume control error: {e}")


# -----------------------------
# Screenshot
# -----------------------------

def take_screenshot():
    if not PYAUTOGUI_AVAILABLE:
        # Fallback: use PIL only
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            os.makedirs(SCREENSHOT_DIR, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(SCREENSHOT_DIR, f"screenshot_{timestamp}.png")
            img.save(path)
            speak(f"Screenshot saved to Pictures folder.")
            print(f"📸 Saved: {path}")
            return
        except Exception as e:
            speak("Sorry, could not take screenshot.")
            print(f"⚠️  Screenshot error: {e}")
            return

    try:
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(SCREENSHOT_DIR, f"screenshot_{timestamp}.png")
        screenshot = pyautogui.screenshot()
        screenshot.save(path)
        speak(f"Screenshot saved to Pictures folder.")
        print(f"📸 Saved: {path}")
    except Exception as e:
        speak("Sorry, could not take screenshot.")
        print(f"⚠️  Screenshot error: {e}")


# -----------------------------
# Open application
# -----------------------------

APP_MAP = {
    "chrome":           r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "google chrome":    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "notepad":          "notepad.exe",
    "note":             "notepad.exe",
    "calculator":       "calc.exe",
    "paint":            "mspaint.exe",
    "file explorer":    "explorer.exe",
    "explorer":         "explorer.exe",
    "vs code":          r"C:\Users\{user}\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    "visual studio code": r"C:\Users\{user}\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    "task manager":     "taskmgr.exe",
    "word":             r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
    "excel":            r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
    "powerpoint":       r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE",
    "power point":      r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE",
}

def open_application(text):
    text_lower = text.lower()
    username = os.environ.get("USERNAME", "user")

    if text_lower.strip() in ["open", "open app", "launch"]:
        speak("Which application would you like me to open?")
        return

    for key, path in APP_MAP.items():
        if key in text_lower:
            path = path.replace("{user}", username)
            try:
                subprocess.Popen([path], shell=True)
                speak(f"Opening {key}.")
                return
            except Exception as e:
                try:
                    os.startfile(path)
                    speak(f"Opening {key}.")
                    return
                except Exception:
                    speak(f"Sorry, I could not open {key}.")
                    print(f"⚠️  App error: {e}")
                    return

    speak("Sorry, I don't know how to open that application.")


# -----------------------------
# Open folder
# -----------------------------

def open_folder(text):
    text_lower = text.lower()
    username = os.environ.get("USERNAME", "user")

    folder_targets = {
        "download": os.path.join(os.path.expanduser("~"), "Downloads"),
        "document": os.path.join(os.path.expanduser("~"), "Documents"),
        "desktop":  os.path.join(os.path.expanduser("~"), "Desktop"),
        "picture":  os.path.join(os.path.expanduser("~"), "Pictures"),
        "music":    os.path.join(os.path.expanduser("~"), "Music"),
        "video":    os.path.join(os.path.expanduser("~"), "Videos"),
    }

    target_path = None
    target_name = "home"

    for key, path in folder_targets.items():
        if key in text_lower:
            target_path = path
            target_name = key + "s"
            break

    if not target_path:
        target_path = os.path.expanduser("~")

    try:
        # Using subprocess with explorer.exe avoids Windows directory startfile permissions issues
        subprocess.Popen(["explorer.exe", target_path])
        speak(f"Opening your {target_name} folder.")
    except Exception as e:
        speak(f"Sorry, could not open the {target_name} folder.")
        print(f"⚠️  Folder error: {e}")


# -----------------------------
# AI answer via Gemini
# -----------------------------

def ask_gemini(question):
    if not gemini_client:
        speak("Gemini AI is not configured. Please set your GEMINI_API_KEY.")
        return

    speak("Let me think about that.")
    try:
        response = gemini_client.models.generate_content(
            model=gemini_model,
            contents=f"Answer this briefly and clearly in 2-3 sentences: {question}"
        )
        answer = response.text.strip()
        print(f"🧠 AI: {answer}")
        speak(answer)
    except Exception as e:
        speak("Sorry, I could not get an answer right now.")
        print(f"⚠️  Gemini error: {e}")


def ask_gemini_summarize(text_to_summarize):
    if not gemini_client:
        speak("Gemini AI is not configured. Please set your GEMINI_API_KEY.")
        return

    speak("Please tell me the text you want me to summarize.")
    user_text = listen()
    if not user_text:
        speak("I did not catch any text to summarize.")
        return

    try:
        response = gemini_client.models.generate_content(
            model=gemini_model,
            contents=f"Summarize this in 2-3 short sentences: {user_text}"
        )
        answer = response.text.strip()
        print(f"📝 Summary: {answer}")
        speak(answer)
    except Exception as e:
        speak("Sorry, I could not summarize that.")
        print(f"⚠️  Gemini error: {e}")


# -----------------------------
# Perform assistant actions
# -----------------------------

def perform_action(intent, text):

    if intent == "greeting":
        if any(w in text for w in ["வணக்கம்", "காலை வணக்கம்", "மதிய வணக்கம்", "மாலை வணக்கம்"]):
            speak("வணக்கம்! நான் உங்களுக்கு எப்படி உதவ முடியும்?")
            return True
        elif "afternoon" in text:
            speak("Good afternoon! How can I help you?")
        elif "evening" in text:
            speak("Good evening! How can I help you?")
        elif "morning" in text:
            speak("Good morning! How can I help you?")
        else:
            hour = datetime.datetime.now().hour
            if hour < 12:
                speak("Good morning! How can I help you?")
            elif hour < 17:
                speak("Good afternoon! How can I help you?")
            else:
                speak("Good evening! How can I help you?")
        return True

    elif intent == "get_time":
        now = datetime.datetime.now().strftime("%I:%M %p")
        speak(f"The current time is {now}.")

    elif intent == "get_date":
        today = datetime.datetime.now().strftime("%A, %d %B %Y")
        speak(f"Today is {today}.")

    elif intent == "open_youtube":
        speak("Opening YouTube.")
        webbrowser.open("https://www.youtube.com")

    elif intent == "web_search":
        prefixes = [
            "search for ", "search ", "look up ", "find ",
            "can you search for ", "please search ", "please find "
        ]
        query = text.strip()
        for prefix in prefixes:
            if query.startswith(prefix):
                query = query[len(prefix):]
                break

        if query:
            speak(f"Searching for {query}.")
            webbrowser.open("https://www.google.com/search?q=" + quote_plus(query))
        else:
            speak("What would you like me to search for?")

    elif intent == "open_app":
        open_application(text)

    elif intent == "open_folder":
        open_folder(text)

    elif intent == "volume_up":
        change_volume("up")

    elif intent == "volume_down":
        change_volume("down")

    elif intent == "volume_mute":
        change_volume("mute")

    elif intent == "volume_unmute":
        change_volume("unmute")

    elif intent == "screenshot":
        take_screenshot()

    elif intent == "ask_ai":
        ask_gemini(text)

    elif intent == "summarize":
        ask_gemini_summarize(text)

    elif intent == "exit":
        speak("Goodbye! Have a great day!")
        return False

    else:
        speak("Sorry, I did not understand that command. Try saying help for a list of commands.")

    return True


# -----------------------------
# Help command
# -----------------------------

def print_help():
    print("""
╔══════════════════════════════════════════════════════╗
║          🎙️  VOICE ASSISTANT - COMMANDS              ║
╠══════════════════════════════════════════════════════╣
║  Greetings   → hello / hi / good morning             ║
║  Time        → what time is it                       ║
║  Date        → what is today's date                  ║
║  YouTube     → open youtube                          ║
║  Web Search  → search for <topic>                    ║
║  Open App    → open chrome / notepad / calculator    ║
║  Open Folder → open downloads / documents folder     ║
║  Volume      → increase/decrease volume / mute       ║
║  Screenshot  → take a screenshot                     ║
║  AI Answer   → what is python / explain loops        ║
║  Summarize   → summarize (then speak your text)      ║
║  Exit        → goodbye / exit / quit                 ║
╚══════════════════════════════════════════════════════╝
""")


# -----------------------------
# Main assistant loop
# -----------------------------

def main():
    print("""
╔══════════════════════════════════════════════════════╗
║       🤖 VOICE ASSISTANT v2.0  - Starting Up         ║
╚══════════════════════════════════════════════════════╝
""")

    # Language selection
    select_language()

    # Startup greeting
    speak("Voice Assistant version 2 started. How can I help you?")

    # Microphone calibration
    if not calibrate_microphone():
        speak("Microphone not found. Exiting.")
        return

    print_help()

    consecutive_failures = 0

    while True:
        text = listen()

        if not text:
            consecutive_failures += 1
            if consecutive_failures >= 5:
                speak("Are you still there? I'm listening.")
                consecutive_failures = 0
            continue

        consecutive_failures = 0

        intent = identify_intent(text)
        print(f"🎯 Detected intent: {intent}")

        if not perform_action(intent, text):
            break


# -----------------------------
# Run assistant
# -----------------------------

if __name__ == "__main__":
    main()
