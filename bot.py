import asyncio
import os
import sys
import logging
import json
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from google import genai
from youtubesearchpython import VideosSearch
from github import Github, Auth

# Enable logging
logging.basicConfig(level=logging.INFO)

# Pull environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")

if not all([BOT_TOKEN, GEMINI_API_KEY, CHANNEL_USERNAME, GITHUB_TOKEN, GITHUB_REPO]):
    logging.error("CRITICAL ERROR: Variables missing! Check your Railway dashboard.")
    sys.exit(1)

# Initialize Clients
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = genai.Client(api_key=GEMINI_API_KEY)

# --- GITHUB DATABASE AUTH FIX ---
auth = Auth.Token(GITHUB_TOKEN)
gh = Github(auth=auth)
repo = gh.get_repo(GITHUB_REPO)

# Load custom study materials
DATA_FILE_PATH = "study_materials.txt"
STUDY_DATA = ""
if os.path.exists(DATA_FILE_PATH):
    with open(DATA_FILE_PATH, "r", encoding="utf-8") as f:
        STUDY_DATA = f.read()
else:
    logging.warning("study_materials.txt not found.")

# --- FSM STATES ---
class PostMaker(StatesGroup):
    drafting = State()
    confirming = State()

# --- GITHUB DATABASE FUNCTIONS ---
def _fetch_scores():
    try:
        file = repo.get_contents("scores.json")
        return json.loads(file.decoded_content.decode()), file.sha
    except:
        return {}, None

def _update_score_sync(user_id: str, username: str, points: int):
    scores, sha = _fetch_scores()
    
    if user_id not in scores:
        scores[user_id] = {"name": username, "score": 0}
    
    scores[user_id]["score"] += points
    content = json.dumps(scores, indent=4)
    
    if sha:
        repo.update_file("scores.json", f"Update {username} score", content, sha)
    else:
        repo.create_file("scores.json", "Initialize scores DB", content)

async def add_points(user_id: int, username: str, points: int):
    """Safely runs the GitHub API call in the background"""
    await asyncio.to_thread(_update_score_sync, str(user_id), username, points)

async def get_leaderboard():
    scores, _ = await asyncio.to_thread(_fetch_scores)
    return scores

# --- PERMISSIONS & KEYBOARDS ---
async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

async def is_admin(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ["administrator", "creator"]
    except:
        return False

def get_subscription_keyboard():
    url = f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}"
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Join Channel to Continue", url=url)]])

def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Grade Essay"), KeyboardButton(text="🗣 Speaking Strategies")],
            [KeyboardButton(text="💬 Grammar Help"), KeyboardButton(text="🎥 Video Lessons")]
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Choose an option or type a message..."
    )

# --- CORE COMMANDS ---
@dp.message(Command("start"))
async def send_welcome(message: types.Message, state: FSMContext):
    await state.clear()
    if not await check_subscription(message.from_user.id):
        await message.answer("👋 Welcome! To use this bot, you must join our channel first.", reply_markup=get_subscription_keyboard())
        return
    await message.answer(
        "👋 Welcome to Multilevel Expert Bot!\n\n"
        "Use the buttons below, send an essay text, or send a **Voice Message** to Beat the Examiner!",
        reply_markup=get_main_keyboard()
    )

@dp.message(Command("leaderboard"))
async def show_leaderboard(message: types.Message):
    if not await check_subscription(message.from_user.id): return
    
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    scores = await get_leaderboard()
    
    if not scores:
        await message.answer("🏆 <b>Leaderboard is currently empty!</b>", parse_mode="HTML")
        return
    
    # Sort scores highest to lowest
    sorted_scores = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
    
    text = "🏆 <b>TOP MULTILEVEL STUDENTS</b> 🏆\n\n"
    for idx, user_data in enumerate(sorted_scores[:10], 1):
        medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else "🎗"
        text += f"{medal} <b>{user_data['name']}</b>: {user_data['score']} pts\n"
        
    await message.answer(text, parse_mode="HTML")

# --- ADMIN PUBLISHING WORKFLOW ---
@dp.message(Command("post"))
async def start_post(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return
    await message.answer("📢 <b>Create a Channel Post</b>\nPlease send the message (text/photo/video) to publish.", parse_mode="HTML")
    await state.set_state(PostMaker.drafting)

@dp.message(PostMaker.drafting)
async def preview_post(message: types.Message, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Publish", callback_data="publish_post")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_post")]
    ])
    await state.update_data(post_message_id=message.message_id)
    await message.answer("👀 <b>Preview:</b>", parse_mode="HTML")
    await message.copy_to(chat_id=message.chat.id, reply_markup=kb)
    await state.set_state(PostMaker.confirming)

@dp.callback_query(PostMaker.confirming)
async def confirm_post(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if callback.data == "publish_post":
        data = await state.get_data()
        try:
            await bot.copy_message(chat_id=CHANNEL_USERNAME, from_chat_id=callback.message.chat.id, message_id=data.get("post_message_id"))
            await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.reply("✅ Post successfully published!")
        except Exception as e:
            await callback.message.reply(f"❌ Error publishing: {e}")
    else:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.reply("❌ Cancelled.")
    await state.clear()

# --- YOUTUBE SKILL ---
@dp.message(Command("video"))
async def search_youtube(message: types.Message, state: FSMContext):
    if await state.get_state() is not None: return
    if not await check_subscription(message.from_user.id): return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Example: <code>/video English grammar tenses</code>", parse_mode="HTML")
        return

    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    try:
        results = VideosSearch(parts[1], limit=3).result()['result']
        if not results:
            await message.answer("Sorry, couldn't find any videos.")
            return

        response_text = f"🎥 <b>Top Videos for:</b> <i>{parts[1]}</i>\n\n"
        for vid in results:
            response_text += f"• <a href='{vid['link']}'>{vid['title']}</a> ({vid['duration']})\n\n"
        await message.answer(response_text, parse_mode="HTML", disable_web_page_preview=True)
    except:
        await message.answer("Sorry, I ran into an issue searching YouTube.")

# --- BUTTON CATCHERS ---
@dp.message(F.text == "📝 Grade Essay")
async def handle_essay_button(message: types.Message):
    await message.answer("Please paste the full text of your essay below!")

@dp.message(F.text == "🗣 Speaking Strategies")
async def handle_speaking_button(message: types.Message):
    await message.answer("Send me a voice message to practice, or ask a specific speaking question!")

@dp.message(F.text == "💬 Grammar Help")
async def handle_grammar_button(message: types.Message):
    await message.answer("What English grammar concept are you struggling with?")

@dp.message(F.text == "🎥 Video Lessons")
async def handle_video_button(message: types.Message):
    await message.answer("Type <code>/video</code> followed by your topic. Example: <code>/video IELTS Speaking</code>", parse_mode="HTML")

# --- BEAT THE EXAMINER (VOICE EVALUATOR) ---
@dp.message(F.voice)
async def process_voice_note(message: types.Message, state: FSMContext):
    if await state.get_state() is not None: return
    if not await check_subscription(message.from_user.id): return

    msg = await message.reply("🎙 <i>Listening to your audio and evaluating...</i>", parse_mode="HTML")
    await bot.send_chat_action(chat_id=message.chat.id, action="record_voice")

    try:
        # Download audio temporarily
        voice_file = await bot.get_file(message.voice.file_id)
        file_path = f"{message.message_id}.ogg"
        await bot.download_file(voice_file.file_path, destination=file_path)

        prompt = f"""
        You are an expert Uzbekistan Multilevel Exam speaking examiner. 
        Transcribe the user's audio and evaluate their speaking performance.
        
        Format strictly using this Telegram HTML structure:
        <b>SPEAKING EVALUATION</b>
        
        <b>Transcript:</b>
        <i>"[Write the text of what they said here]"</i>

        <b>Score Breakdown:</b>
        • Fluency & Coherence: [Score]/9
        • Lexical Resource (Vocab): [Score]/9
        • Grammatical Range: [Score]/9
        • Pronunciation: [Score]/9

        <b>Feedback:</b>
        ✅ [One thing they did well]
        ⚠️ [One specific area to improve]
        """
        
        # Upload and generate
        uploaded_audio = await asyncio.to_thread(client.files.upload, file=file_path)
        response = await client.aio.models.generate_content(
            model="gemini-3.5-flash",
            contents=[prompt, uploaded_audio]
        )
        
        # Cleanup file and send result
        os.remove(file_path)
        await msg.edit_text(response.text, parse_mode="HTML")
        
        # Gamification: Add 5 points for completing a speaking challenge!
        await add_points(message.from_user.id, message.from_user.first_name, 5)
        await message.answer("🎉 <b>+5 Points</b> added to your profile for practicing speaking! Check /leaderboard.", parse_mode="HTML")

    except Exception as e:
        logging.error(f"Audio Error: {e}")
        await msg.edit_text("Sorry, I could not process your voice note. Please try again.")

# --- ESSAY GRADING & TEXT CHAT ---
@dp.message(F.text)
async def process_user_text(message: types.Message, state: FSMContext):
    if await state.get_state() is not None: return 
    if not await check_subscription(message.from_user.id): return

    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    system_prompt = f"""
    You are an expert English Tutor and Examiner for the Uzbekistan Multilevel Exam.
    Analyze the user's input below and choose the correct mode to respond:

    MODE 1: ESSAY EVALUATION
    Grade the text strictly on Multilevel criteria. Give a score /24. Highlight 2 strengths, 2 weaknesses, provide 2 line edits, and one actionable next step. Format heavily with emojis, <b>, and <i>.
    
    MODE 2: SPEAKING / GRAMMAR Q&A
    Answer their English questions clearly using Telegram HTML formatting. Pull from REFERENCE DATA if asked about strategies.

    === REFERENCE DATA ===
    {STUDY_DATA}
    === END REFERENCE DATA ===

    User Input:
    {message.text}
    """
    try:
        response = await client.aio.models.generate_content(model="gemini-3.5-flash", contents=system_prompt)
        await message.reply(response.text, parse_mode="HTML")
        
        # Gamification: Add 10 points for writing an essay (rough check for length)
        if len(message.text.split()) > 100:
            await add_points(message.from_user.id, message.from_user.first_name, 10)
            await message.answer("📝 <b>+10 Points</b> added for submitting a full essay! Check /leaderboard.", parse_mode="HTML")

    except Exception as e:
        logging.error(f"Text Error: {e}")
        await message.reply("The AI is experiencing high demand. Please try again in 60 seconds.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
