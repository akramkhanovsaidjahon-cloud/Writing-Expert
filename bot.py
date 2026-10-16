import asyncio
import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from google import genai

# Enable logging so we can see errors in Railway's dashboard
logging.basicConfig(level=logging.INFO)

# Pull API keys from Railway's Environment Variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Initialize Telegram Bot and Dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Initialize Google Gen AI Client
client = genai.Client(api_key=GEMINI_API_KEY)

@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    await message.answer("Send me your essay, and I will grade it and provide corrections!")

@dp.message()
async def evaluate_essay(message: types.Message):
    # Ignore non-text messages for now
    if not message.text:
        await message.answer("Please send me the text of your essay to evaluate.")
        return

    user_essay = message.text
    
    # Show the "typing..." indicator in Telegram
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    # The grading rubric
    system_prompt = f"""
    Act as an expert English teacher. Grade this essay. 
    Provide a score out of 100, identify specific grammar mistakes, and suggest structural improvements.
    Format your response clearly.
    
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
        await message.reply("Sorry, I ran into an issue grading your essay. Please try again.")

async def main():
    # Start the bot using Long Polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
