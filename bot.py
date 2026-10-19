import asyncio
import os
import sys
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from google import genai
from youtubesearchpython import VideosSearch

# Enable logging
logging.basicConfig(level=logging.INFO)

# Pull environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")

if not BOT_TOKEN or not GEMINI_API_KEY or not CHANNEL_USERNAME:
    logging.error("CRITICAL ERROR: Variables missing!")
    sys.exit(1)

# Load custom study materials from the local file
DATA_FILE_PATH = "study_materials.txt"
STUDY_DATA = ""
if os.path.exists(DATA_FILE_PATH):
    with open(DATA_FILE_PATH, "r", encoding="utf-8") as f:
        STUDY_DATA = f.read()
    logging.info("Study materials loaded successfully.")
else:
    logging.warning("study_materials.txt not found. Running without custom samples.")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = genai.Client(api_key=GEMINI_API_KEY)

async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logging.error(f"Could not check subscription: {e}")
        return False

def get_subscription_keyboard():
    url = f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Join Channel to Continue", url=url)]
    ])

# --- NEW: The Large Grid Keyboard ---
def get_main_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Grade Essay"), KeyboardButton(text="🗣 Speaking Strategies")],
            [KeyboardButton(text="💬 Grammar Help"), KeyboardButton(text="🎥 Video Lessons")]
        ],
        resize_keyboard=True,
        is_persistent=True, # Keeps the 4-square icon visible in the chat bar
        input_field_placeholder="Choose an option or type a message..."
    )
    return keyboard

@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    if not await check_subscription(message.from_user.id):
        await message.answer(
            "👋 Welcome! To use this bot, you must join our channel first.",
            reply_markup=get_subscription_keyboard()
        )
        return

    await message.answer(
        "👋 Welcome to Multilevel Expert Bot!\n\n"
        "Use the buttons below to navigate, or simply send me your essay or questions directly!",
        reply_markup=get_main_keyboard() # Shows the large buttons to the user
    )

# --- NEW: Catching Button Clicks ---
@dp.message(F.text == "📝 Grade Essay")
async def handle_essay_button(message: types.Message):
    if not await check_subscription(message.from_user.id):
        return
    await message.answer("Please paste the full text of your essay below, and I will evaluate it against the official Multilevel criteria!")

@dp.message(F.text == "💬 Grammar Help")
async def handle_grammar_button(message: types.Message):
    if not await check_subscription(message.from_user.id):
        return
    await message.answer("What English grammar concept are you struggling with? Type your question below and I will explain it.")

@dp.message(F.text == "🎥 Video Lessons")
async def handle_video_button(message: types.Message):
    if not await check_subscription(message.from_user.id):
        return
    await message.answer("To search for a video lesson, type <code>/video</code> followed by your topic.\n\nExample: <code>/video IELTS Speaking Part 2</code>", parse_mode="HTML")

# --- YOUTUBE VIDEO SKILL ---
@dp.message(Command("video"))
async def search_youtube(message: types.Message):
    if not await check_subscription(message.from_user.id):
        await message.answer("You must be subscribed to use the bot.", reply_markup=get_subscription_keyboard())
        return

    command_parts = message.text.split(maxsplit=1)
    if len(command_parts) < 2:
        await message.answer("Please tell me what to search for! Example: <code>/video English grammar tenses</code>", parse_mode="HTML")
        return

    search_query = command_parts[1]
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    try:
        videos_search = VideosSearch(search_query, limit=3)
        results = videos_search.result()['result']
        
        if not results:
            await message.answer(f"Sorry, I couldn't find any videos for '<b>{search_query}</b>'.", parse_mode="HTML")
            return

        response_text = f"🎥 <b>Top YouTube Videos for:</b> <i>{search_query}</i>\n\n"
        for vid in results:
            title = vid['title']
            link = vid['link']
            duration = vid['duration']
            response_text += f"• <a href='{link}'>{title}</a> ({duration})\n\n"

        await message.answer(response_text, parse_mode="HTML")

    except Exception as e:
        logging.error(f"Error searching YouTube: {e}")
        await message.answer("Sorry, I ran into an issue searching YouTube. Please try again.")

# --- ESSAY GRADING & AI CHAT SKILL ---
@dp.message()
async def process_user_text(message: types.Message):
    if not await check_subscription(message.from_user.id):
        await message.answer("You must be subscribed to use the bot.", reply_markup=get_subscription_keyboard())
        return

    if not message.text:
        await message.answer("Please send written text.")
        return

    user_text = message.text
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    system_prompt = f"""
    You are an expert English Tutor and Examiner for the Uzbekistan Multilevel Exam.
    Analyze the user's input below and choose the correct mode to respond:

    MODE 1: ESSAY EVALUATION (TASK 2)
    If the user submits an essay:
    - Grade it based strictly on Multilevel criteria (penalize under 188 words, zero mark under 40 words).
    - Format your response EXACTLY using the Telegram HTML structure below. Do NOT use markdown code blocks (```).
    - Ensure all tags (<b>, <i>, <s>, <blockquote>) are properly closed.

    <b>ESSAY REVIEW</b>
    <b>[Short Title Summarizing the Essay]</b>
    [1-2 sentence overall summary of the essay's quality]

    <b>Score breakdown</b>
    • Task Achievement: [Score]/9
    • Grammar Range: [Score]/9
    • Vocabulary: [Score]/9
    • Coherence: [Score]/9
    <i>Estimated Task 2 Raw Score: [Score]/24</i>

    <b>What's working</b>
    ✅ [Strength 1]
    ✅ [Strength 2]

    <b>What to fix</b>
    1️⃣ <b>[Issue]</b> [🔴 High / 🟡 Medium / 🟢 Low priority]
    [Explanation]

    2️⃣ <b>[Issue]</b> [🔴 High / 🟡 Medium / 🟢 Low priority]
    [Explanation]

    <b>Line edits</b>
    <blockquote><b>BEFORE:</b> <s>[Quote original text with error]</s>
    <b>AFTER:</b> [Corrected text]
    <i>[Brief explanation of why it was changed]</i></blockquote>

    <blockquote><b>BEFORE:</b> <s>[Quote original text with error]</s>
    <b>AFTER:</b> [Corrected text]
    <i>[Brief explanation of why it was changed]</i></blockquote>

    <b>Next step</b>
    ▶️ [One actionable instruction for revision]

    MODE 2: SPEAKING SAMPLES AND STRATEGIES
    If the user asks for speaking topics, speaking practice, or speaking exam strategies (e.g., they click the "🗣 Speaking Strategies" button):
    - Pull samples and strategies ONLY from the provided REFERENCE DATA below.
    - Format response using standard Telegram HTML (<b> for bold, <i> for italics).
    
    MODE 3: GENERAL ENGLISH QUESTIONS
    If the user asks a general English or grammar question, use your native English knowledge to explain it clearly using standard Telegram HTML formatting.

    === START OF REFERENCE DATA FOR MODE 2 ===
    {STUDY_DATA}
    === END OF REFERENCE DATA ===

    User Input:
    {user_text}
    """
    try:
        response = await client.aio.models.generate_content(model="gemini-3.5-flash", contents=system_prompt)
        await message.reply(response.text, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Error: {e}")
        if "503" in str(e) or "demand" in str(e).lower():
            await message.reply("The AI is experiencing high demand. Please try again in 60 seconds.")
        else:
            await message.reply("Sorry, I ran into an issue rendering the review. Please try again.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
