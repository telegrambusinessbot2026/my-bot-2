import logging
import asyncio
import os
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# ---------------- CONFIGURATION (Env Vars) ----------------
# Render-ൽ കൊടുക്കേണ്ട പേരുകൾ:
BOT1_TOKEN = os.getenv('8127783555:AAE7dIqBVSd_EW2p-QL_6KEVVvvS4KLH3fc')      # (Group Delete Bot Token)
BOT2_TOKEN = os.getenv('8489791050:AAE_SnRSbqfDAn0JSd_sHBk9df_jHbQ1cas')      # (DM Poster Bot Token)
OWNER_ID = str(os.getenv('7639633018'))     # (Your ID - String)
TARGET_GROUP_ID = int(os.getenv('-1003621584117')) # (Bot പ്രവർത്തിക്കേണ്ട ഗ്രൂപ്പ് ID)
PORT = int(os.getenv('PORT', 8080))       # (Render Port)
LOOP_TIME = 600                           # (10 Minutes)
# ----------------------------------------------------------

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ==============================================================================
#                               BOT 1 LOGIC (Group Cleaner)
# ==============================================================================

# നിരോധിത വാക്കുകൾ
restricted_words = ['tm', 'pm', 'dm', 'message', 'inbox']

async def bot1_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Security Bot is Active!")

async def add_restricted_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    # ഓണർക്ക് മാത്രമേ വാക്കുകൾ ആഡ് ചെയ്യാൻ പറ്റൂ
    if user_id == OWNER_ID:
        if context.args:
            new_word = context.args[0].lower()
            if new_word not in restricted_words:
                restricted_words.append(new_word)
                await update.message.reply_text(f"Added '{new_word}' to restricted words.")
            else:
                await update.message.reply_text(f"'{new_word}' is already in the list.")
        else:
            await update.message.reply_text("Please specify a word.")
    else:
        await update.message.reply_text("⚠️ You are not authorized.")

async def delete_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    message = update.message
    chat_id = update.effective_chat.id
    user = update.effective_user
    text = message.text.lower()

    # --- SECURITY CHECK: വേറെ ഗ്രൂപ്പുകളിൽ വർക്ക് ചെയ്യാതിരിക്കാൻ ---
    if chat_id != TARGET_GROUP_ID:
        return # നമ്മുടെ ഗ്രൂപ്പ് അല്ലെങ്കിൽ ഒന്നും ചെയ്യില്ല
    # ----------------------------------------------------------

    # അഡ്മിൻ ആണെങ്കിൽ ഡിലീറ്റ് ചെയ്യേണ്ട
    if update.effective_chat.type in ['group', 'supergroup']:
        try:
            member = await context.bot.get_chat_member(chat_id, user.id)
            if member.status in ['administrator', 'creator']:
                return
        except:
            pass

    # വാക്കുകൾ ചെക്ക് ചെയ്യുന്നു
    for word in restricted_words:
        if word in text:
            try:
                await context.bot.delete_message(chat_id, message.message_id)
            except Exception as e:
                print(f"Error deleting: {e}")
            break

# ==============================================================================
#                               BOT 2 LOGIC (DM Poster & Loop)
# ==============================================================================

current_loop_task = None
last_loop_message_id = None

async def handle_dm_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_loop_task, last_loop_message_id
    
    # ഓണർ അല്ലെങ്കിൽ, പ്രൈവറ്റ് ചാറ്റ് അല്ലെങ്കിൽ മറുപടി നൽകില്ല
    if update.effective_chat.type != 'private' or str(update.effective_user.id) != OWNER_ID:
        return

    msg = update.message
    full_text = msg.text or msg.caption or ""

    # ലൂപ്പ് നിർത്താൻ
    if full_text.lower() == "stop":
        if current_loop_task:
            current_loop_task.cancel()
            current_loop_task = None
            last_loop_message_id = None
            await msg.reply_text("🛑 Loop stopped.")
        return

    clean_text = full_text.replace("#loop", "").replace("#Loop", "").strip()
    post_content = clean_text
    reply_markup = None

    # ബട്ടൺ വേർതിരിക്കുന്നു
    if "===" in clean_text:
        try:
            parts = clean_text.split("===", 1)
            post_content = parts[0].strip()
            button_section = parts[1].strip()
            keyboard = []
            for line in button_section.split('\n'):
                if "|" in line:
                    btn_text, btn_url = line.split("|", 1)
                    keyboard.append([InlineKeyboardButton(btn_text.strip(), url=btn_url.strip())])
            if keyboard:
                reply_markup = InlineKeyboardMarkup(keyboard)
        except:
            pass

    # #loop ഉണ്ടെങ്കിൽ ഓട്ടോമാറ്റിക് പോസ്റ്റിംഗിലേക്ക്
    if "#loop" in full_text.lower():
        if current_loop_task:
            current_loop_task.cancel()
        await msg.reply_text("🔄 Loop started (Every 10 mins).")
        current_loop_task = asyncio.create_task(run_loop(context, msg, post_content, reply_markup))
    else:
        await send_post(context, msg, post_content, reply_markup)
        await msg.reply_text("✅ Sent to group.")

async def send_post(context, original_msg, content, markup):
    if original_msg.photo:
        return await context.bot.send_photo(chat_id=TARGET_GROUP_ID, photo=original_msg.photo[-1].file_id, caption=content, reply_markup=markup)
    else:
        return await context.bot.send_message(chat_id=TARGET_GROUP_ID, text=content, reply_markup=markup)

async def run_loop(context, original_msg, content, markup):
    global last_loop_message_id
    while True:
        try:
            if last_loop_message_id:
                try: await context.bot.delete_message(chat_id=TARGET_GROUP_ID, message_id=last_loop_message_id)
                except: pass
            sent_msg = await send_post(context, original_msg, content, markup)
            last_loop_message_id = sent_msg.message_id
        except Exception as e:
            print(f"Loop Error: {e}")
        await asyncio.sleep(LOOP_TIME)

# ==============================================================================
#                               RENDER SERVER & MAIN
# ==============================================================================

async def health_check(request):
    return web.Response(text="Both Bots are Running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()

async def main():
    # 1. വെബ് സെർവർ സ്റ്റാർട്ട് ചെയ്യുന്നു
    await start_web_server()
    
    # 2. Bot 1 (Group Cleaner) സെറ്റപ്പ്
    app1 = ApplicationBuilder().token(BOT1_TOKEN).build()
    app1.add_handler(CommandHandler('start', bot1_start))
    app1.add_handler(CommandHandler('addword', add_restricted_word))
    app1.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), delete_messages))
    
    await app1.initialize()
    await app1.start()
    await app1.updater.start_polling()
    print("✅ Bot 1 (Group Cleaner) Started")

    # 3. Bot 2 (DM Poster) സെറ്റപ്പ്
    app2 = ApplicationBuilder().token(BOT2_TOKEN).build()
    app2.add_handler(MessageHandler(filters.ChatType.PRIVATE & (filters.TEXT | filters.PHOTO), handle_dm_post))
    
    await app2.initialize()
    await app2.start()
    await app2.updater.start_polling()
    print("✅ Bot 2 (DM Poster) Started")

    # നിർത്താതെ പ്രവർത്തിക്കാൻ
    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
