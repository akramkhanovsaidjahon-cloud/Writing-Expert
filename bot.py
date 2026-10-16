import asyncio
import os
import sys
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from google import genai

# Enable logging so we can see errors in Railway's dashboard
logging.basicConfig(level=logging.INFO)

# Pull API keys from Railway's Environment Variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Safety check to prevent the bot from crashing silently if variables are missing
if not BOT_TOKEN:
    logging.error("CRITICAL ERROR: BOT_TOKEN is missing! Please add it to your Railway variables.")
    sys.exit(1)

if not GEMINI_API_KEY:
    logging.error("CRITICAL ERROR: GEMINI_API_KEY is missing! Please add it to your Railway variables.")
    sys.exit(1)

# Initialize Telegram Bot and Dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Initialize Google Gen AI Client
client = genai.Client(api_key=GEMINI_API_KEY)

@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    await message.answer("Send me your Multilevel English Task 2 essay, and I will grade it according to the official criteria!")

@dp.message()
async def evaluate_essay(message: types.Message):
    # Ignore non-text messages for now
    if not message.text:
        await message.answer("Please send me the text of your essay to evaluate.")
        return

    user_essay = message.text
    
    # Show the "typing..." indicator in Telegram
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    # The grading rubric based on Uzbekistan Multilevel English Exam criteria
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
        # Ask Gemini to grade the essay
        response = client.models.generate_content(
            model="gemini-3.5-flash", 
            contents=system_prompt,
        )
        
        # Send the feedback back to Telegram
        await message.reply(response.text)
        
    except Exception as e:
        logging.error(f"Error grading essay: {e}")
        # Custom error handling for Gemini API high-demand spikes
        if "503" in str(e) or "demand" in str(e).lower():
            await message.reply("The AI grader is currently experiencing high demand. Please wait 60 seconds and try sending your essay again.")
        else:
            await message.reply("Sorry, I ran into an issue grading your essay. Please try again.")

async def main():
    # Start the bot using Long Polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
