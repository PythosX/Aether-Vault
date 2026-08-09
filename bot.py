import os
import sqlite3
from werkzeug.security import check_password_hash
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///aethervault.db')

def get_db():
    if DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://"):
        import psycopg2
        url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        conn = psycopg2.connect(url)
        return conn, "postgres"
    else:
        db_path = DATABASE_URL.replace("sqlite:///", "")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn, "sqlite"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn, db_type = get_db()
    c = conn.cursor()
    c.execute("SELECT username FROM users")
    raw_users = c.fetchall()
    conn.close()

    users = [u[0] if db_type == "postgres" else u['username'] for u in raw_users]

    if not users:
        await update.message.reply_text("⚡ **AetherVault**: No registered accounts found.")
        return

    keyboard = [[InlineKeyboardButton(u, callback_data=f"user_{u}")] for u in users]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🛡️ **AetherVault System Access**\nSelect your username:", reply_markup=reply_markup, parse_mode="Markdown")

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    selected_username = query.data.replace("user_", "")
    context.user_data['selected_user'] = selected_username
    context.user_data['state'] = 'AWAIT_PASSWORD'
    
    await query.edit_message_text(f"Target Vault: **{selected_username}**\n\n🔑 Send your password to unlock files:", parse_mode="Markdown")

async def handle_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('state') == 'AWAIT_PASSWORD':
        entered_password = update.message.text
        username = context.user_data.get('selected_user')

        conn, db_type = get_db()
        c = conn.cursor()
        
        if db_type == "postgres":
            c.execute("SELECT id, password FROM users WHERE username = %s", (username,))
            res = c.fetchone()
            user = {'id': res[0], 'password': res[1]} if res else None
        else:
            c.execute("SELECT id, password FROM users WHERE username = ?", (username,))
            user = c.fetchone()

        if user and check_password_hash(user['password'], entered_password):
            user_id = user['id']
            if db_type == "postgres":
                c.execute("SELECT file_id, file_name FROM files WHERE user_id = %s", (user_id,))
                raw_files = c.fetchall()
                files = [{'file_id': f[0], 'file_name': f[1]} for f in raw_files]
            else:
                c.execute("SELECT file_id, file_name FROM files WHERE user_id = ?", (user_id,))
                files = c.fetchall()
            conn.close()

            context.user_data['state'] = None
            if not files:
                await update.message.reply_text("✅ Vault Authenticated! Storage is empty.")
                return

            await update.message.reply_text(f"✅ Vault Authenticated! Sending {len(files)} stored document(s)...")
            for f in files:
                await update.message.reply_document(document=f['file_id'], filename=f['file_name'])
        else:
            conn.close()
            await update.message.reply_text("❌ Authentication Failed! Incorrect password. Use /start to try again.")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_click))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_password))
    
    print("AetherVault Bot Active...")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()

