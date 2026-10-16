import asyncio
import os
import sys
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from google import genai

# Enable logging
logging.basicConfig(level=logging.INFO)

# Pull variables from Railway
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME") 

# Safety checks
if not BOT_TOKEN or not GEMINI_API_KEY or not CHANNEL_USERNAME:
    logging.error("CRITICAL ERROR: BOT_TOKEN, GEMINI_API_KEY, or CHANNEL_USERNAME is missing from Railway variables!")
    sys.exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = genai.Client(api_key=GEMINI_API_KEY)

# Helper function to check if the user is in the channel
async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        # Status 'left', 'kicked', or 'not_found' means they are not subscribed
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logging.error(f"Could not check subscription: {e}")
        return False

# Generate an inline keyboard with a link to the channel
def get_subscription_keyboard():
    # Remove the '@' to create a valid t.me link
    url = f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Join Channel to Continue", url=url)]
    ])
    return keyboard

@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    # Enforce channel join before welcoming
    if not await check_subscription(message.from_user.id):
        await message.answer(
            "👋 Welcome! To use this bot and grade your essays, you must first join our channel. Please join using the button below, then send /start again.",
            reply_markup=get_subscription_keyboard()
        )
        return

    await message.answer("Send me your Multilevel English Task 2 essay, and I will grade it according to the official criteria!")

@dp.message()
async def evaluate_essay(message: types.Message):
    # Enforce channel join before evaluating any text
    if not await check_subscription(message.from_user.id):
        await message.answer(
            "You need to be subscribed to our channel to check essays. Please join and try again!",
            reply_markup=get_subscription_keyboard()
        )
        return

    if not message.text:
        await message.answer("Please send me the text of your essay to evaluate.")
        return

    user_essay = message.text
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    system_prompt = f"""
    You are an expert examiner for the Uzbekistan Multilevel English Exam. Grade the following Task 2 essay based strictly on the official assessment criteria.

    1. ZERO MARK CONDITIONS: 
    Assign a 0 immediately if the response is not written, completely off topic, fully plagiarized or memorized, or less than 40 words in length.
    
    2. SCORING CRITERIA (Band 2 to 9):
    Evaluate the essay across these four distinct categories:
    * Task Achievement: Does it present a clear position, fully extend ideas, and observe academic style?
    * Grammar Range and Accuracy: Does it use a variety of complex structures with full control and minimal errors?
    * Vocabulary Range and Appropriacy: Does it use a wide range of vocabulary with precision, flexibility, and effective paraphrasing?
    * Coherence and Cohesion: Is the text a well-organised whole with a variety of cohesive devices and proper paragraphing?

    3. WORD COUNT PENALTIES (TASK 2):
    * 188-225 words: Limit Task Achievement to Band 7 features.
    * 125-187 words: Limit Task Achievement to Band 5 features.
    * 76-125 words: Limit Task Achievement to Band 3 features.

    4. FINAL CALCULATION:
    Task 2 accounts for 67% (24 points) of the total writing section score. 

    Provide your response in this format:
    **Overall Band Score:** [2-9]
    **Estimated Task 2 Raw Score:** [Out of 24]
    
    **Category Breakdown:**
    * Task Achievement: [Score] - [Reason]
    * Grammar: [Score] - [Reason]
    * Vocabulary: [Score] - [Reason]
    * Coherence: [Score] - [Reason]

    **Key Corrections:**
    [List 3-5 specific grammar or vocabulary mistakes and provide the corrected version]
    
    Essay to grade:
    {user_essay}
    """
    
    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash", 
            contents=system_prompt,
        )
        await message.reply(response.text)
        
    except Exception as e:
        logging.error(f"Error grading essay: {e}")
        if "503" in str(e) or "demand" in str(e).lower():
            await message.reply("The AI grader is currently experiencing high demand. Please wait 60 seconds and try sending your essay again.")
        else:
            await message.reply("Sorry, I ran into an issue grading your essay. Please try again.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
