import os
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler
from telegram.error import BadRequest
import logging
import sqlite3
import asyncio
import nest_asyncio
from typing import Optional, List, Dict, Tuple
from datetime import datetime

# Применяем исправление для Replit
nest_asyncio.apply()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота из переменных окружения
BOT_TOKEN = os.environ.get('BOT_TOKEN')

# Проверка токена
if not BOT_TOKEN:
    logger.error("BOT_TOKEN не установлен! Добавьте его в Secrets Replit")
    print("❌ ОШИБКА: BOT_TOKEN не найден!")
    print("💡 Решение: Добавьте BOT_TOKEN в Secrets Replit")
    # Не вызываем raise, чтобы бот мог перезапускаться

# Этапы разговора
ROLE = 0
PSY_NAME, PSY_GENDER, PSY_AGE, PSY_EDUCATION, PSY_ABOUT, PSY_APPROACH, PSY_REQUESTS, PSY_PRICE, PSY_PHOTO = range(1, 10)
CLIENT_NAME, CLIENT_GENDER, CLIENT_AGE, CLIENT_REQUEST = range(10, 14)
EDIT_CHOICE = 20
EDIT_PSY_NAME, EDIT_PSY_GENDER, EDIT_PSY_AGE, EDIT_PSY_EDUCATION, EDIT_PSY_ABOUT, EDIT_PSY_APPROACH, EDIT_PSY_REQUESTS, EDIT_PSY_PRICE, EDIT_PSY_PHOTO = range(21, 30)
EDIT_CLIENT_NAME, EDIT_CLIENT_GENDER, EDIT_CLIENT_AGE, EDIT_CLIENT_REQUEST = range(30, 34)

# ========== БАЗА ДАННЫХ SQLite ==========

class Database:
    def __init__(self, db_path: str = "psymatch.db"):
        self.db_path = db_path
        self.init_db()
    
    def get_connection(self):
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as e:
            logger.error(f"Database connection error: {e}")
            raise
    
    def init_db(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                role TEXT NOT NULL,
                registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица профилей психологов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS psychologist_profiles (
                user_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                gender TEXT,
                age INTEGER,
                education TEXT,
                about_me TEXT,
                approach TEXT,
                work_requests TEXT,
                price TEXT,
                photo_file_id TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        
        # Таблица профилей клиентов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS client_profiles (
                user_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                gender TEXT,
                age INTEGER,
                request TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        
        # Таблица лайков
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS likes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_user_id INTEGER NOT NULL,
                to_user_id INTEGER NOT NULL,
                liked_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_mutual INTEGER DEFAULT 0,
                UNIQUE(from_user_id, to_user_id),
                FOREIGN KEY (from_user_id) REFERENCES users(user_id),
                FOREIGN KEY (to_user_id) REFERENCES users(user_id)
            )
        ''')
        
        # Таблица просмотренных профилей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS profiles_viewed (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                viewed_user_id INTEGER NOT NULL,
                viewed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, viewed_user_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (viewed_user_id) REFERENCES users(user_id)
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")
    
    def create_user(self, user_id: int, username: Optional[str], first_name: Optional[str], last_name: Optional[str], role: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO users (user_id, username, first_name, last_name, role)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name, role))
            conn.commit()
            logger.info(f"User created: {user_id}, role: {role}")
        except sqlite3.Error as e:
            logger.error(f"Error creating user: {e}")
        finally:
            conn.close()
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    
    def update_last_active(self, user_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users SET last_active = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (user_id,))
        conn.commit()
        conn.close()
    
    def save_psychologist_profile(self, user_id: int, name: str, gender: str, age: str, 
                                education: str, about_me: str, approach: str, 
                                work_requests: str, price: str, photo_file_id: Optional[str] = None):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO psychologist_profiles 
            (user_id, name, gender, age, education, about_me, approach, work_requests, price, photo_file_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, name, gender, age, education, about_me, approach, work_requests, price, photo_file_id))
        conn.commit()
        conn.close()
        logger.info(f"Psychologist profile saved: {user_id}")
    
    def save_client_profile(self, user_id: int, name: str, gender: str, age: str, request: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO client_profiles 
            (user_id, name, gender, age, request)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, name, gender, age, request))
        conn.commit()
        conn.close()
        logger.info(f"Client profile saved: {user_id}")
    
    def get_psychologist_profile(self, user_id: int) -> Optional[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT p.*, u.username, u.first_name, u.last_name 
            FROM psychologist_profiles p
            LEFT JOIN users u ON p.user_id = u.user_id
            WHERE p.user_id = ?
        ''', (user_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    
    def get_client_profile(self, user_id: int) -> Optional[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.*, u.username, u.first_name, u.last_name 
            FROM client_profiles c
            LEFT JOIN users u ON c.user_id = u.user_id
            WHERE c.user_id = ?
        ''', (user_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    
    def get_all_psychologists(self) -> List[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT p.*, u.username, u.first_name, u.last_name 
            FROM psychologist_profiles p
            JOIN users u ON p.user_id = u.user_id
            WHERE u.role = 'psychologist'
        ''')
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def get_all_clients(self) -> List[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.*, u.username, u.first_name, u.last_name 
            FROM client_profiles c
            JOIN users u ON c.user_id = u.user_id
            WHERE u.role = 'client'
        ''')
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def create_like(self, from_user_id: int, to_user_id: int) -> Tuple[bool, bool]:
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Проверяем, есть ли уже лайк
        cursor.execute('''
            SELECT id FROM likes 
            WHERE from_user_id = ? AND to_user_id = ?
        ''', (from_user_id, to_user_id))
        if cursor.fetchone():
            conn.close()
            return False, False
        
        # Создаем лайк
        cursor.execute('''
            INSERT INTO likes (from_user_id, to_user_id)
            VALUES (?, ?)
        ''', (from_user_id, to_user_id))
        
        # Проверяем взаимность
        cursor.execute('''
            SELECT id FROM likes 
            WHERE from_user_id = ? AND to_user_id = ?
        ''', (to_user_id, from_user_id))
        is_mutual = cursor.fetchone() is not None
        
        if is_mutual:
            cursor.execute('''
                UPDATE likes SET is_mutual = 1 
                WHERE (from_user_id = ? AND to_user_id = ?) 
                OR (from_user_id = ? AND to_user_id = ?)
            ''', (from_user_id, to_user_id, to_user_id, from_user_id))
        
        conn.commit()
        conn.close()
        logger.info(f"Like created: {from_user_id} -> {to_user_id}, mutual: {is_mutual}")
        return True, is_mutual
    
    def get_likes_for_user(self, user_id: int) -> List[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT l.*, u.username, u.first_name, u.last_name, u.role
            FROM likes l
            JOIN users u ON l.from_user_id = u.user_id
            WHERE l.to_user_id = ?
            ORDER BY l.liked_date DESC
        ''', (user_id,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def get_mutual_likes(self, user_id: int) -> List[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT u.user_id, u.username, u.first_name, u.last_name, u.role,
                   CASE 
                     WHEN u.role = 'psychologist' THEN p.name
                     WHEN u.role = 'client' THEN c.name
                   END as name
            FROM likes l1
            JOIN likes l2 ON l1.from_user_id = l2.to_user_id AND l1.to_user_id = l2.from_user_id
            JOIN users u ON l2.from_user_id = u.user_id
            LEFT JOIN psychologist_profiles p ON u.user_id = p.user_id
            LEFT JOIN client_profiles c ON u.user_id = c.user_id
            WHERE l1.from_user_id = ? AND l1.is_mutual = 1
        ''', (user_id,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def add_viewed_profile(self, user_id: int, viewed_user_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO profiles_viewed (user_id, viewed_user_id)
            VALUES (?, ?)
        ''', (user_id, viewed_user_id))
        conn.commit()
        conn.close()
    
    def get_viewed_profiles(self, user_id: int) -> List[int]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT viewed_user_id FROM profiles_viewed 
            WHERE user_id = ?
        ''', (user_id,))
        rows = cursor.fetchall()
        conn.close()
        return [row['viewed_user_id'] for row in rows]
    
    def get_user_likes(self, user_id: int) -> List[int]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT to_user_id FROM likes 
            WHERE from_user_id = ?
        ''', (user_id,))
        rows = cursor.fetchall()
        conn.close()
        return [row['to_user_id'] for row in rows]
    
    def check_mutual_like(self, user1_id: int, user2_id: int) -> bool:
        """Проверяет, есть ли взаимный лайк между двумя пользователями"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) as count FROM likes 
            WHERE (from_user_id = ? AND to_user_id = ?) 
            OR (from_user_id = ? AND to_user_id = ?)
        ''', (user1_id, user2_id, user2_id, user1_id))
        result = cursor.fetchone()
        conn.close()
        return result['count'] == 2
    
    def get_statistics(self) -> Dict:
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) as count FROM users WHERE role = 'psychologist'")
        psychologists_count = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM users WHERE role = 'client'")
        clients_count = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM likes WHERE is_mutual = 1")
        mutual_matches = cursor.fetchone()['count'] // 2
        
        cursor.execute("SELECT COUNT(*) as count FROM likes")
        total_likes = cursor.fetchone()['count']
        
        conn.close()
        
        return {
            'psychologists_count': psychologists_count,
            'clients_count': clients_count,
            'mutual_matches': mutual_matches,
            'total_likes': total_likes
        }
    
    def reset_viewed_profiles(self, user_id: int):
        """Сброс просмотренных профилей"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM profiles_viewed WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        logger.info(f"Viewed profiles reset for user: {user_id}")

# Создаем экземпляр базы данных
db = Database()

# ========== СИСТЕМА УВЕДОМЛЕНИЙ ==========

async def send_like_notification(context: ContextTypes.DEFAULT_TYPE, from_user_id: int, to_user_id: int):
    """Отправка уведомления о новом лайке"""
    try:
        # Получаем информацию о пользователе, который поставил лайк
        from_user = db.get_user(from_user_id)
        from_profile = None
        
        if from_user['role'] == 'psychologist':
            from_profile = db.get_psychologist_profile(from_user_id)
        else:
            from_profile = db.get_client_profile(from_user_id)
        
        from_user_name = from_profile.get('name', 'пользователь') if from_profile else 'пользователь'
        from_user_role = "психолог" if from_user['role'] == 'psychologist' else "клиент"
        
        # Формируем сообщение
        message = f"""
❤️ **У вас новый лайк!**

👤 **{from_user_name}** ({from_user_role}) поставил(а) вам лайк.

💫 Загляните в раздел "Мои мэтчи", чтобы посмотреть анкету и ответить взаимностью!
        """
        
        # Отправляем уведомление
        await context.bot.send_message(
            chat_id=to_user_id,
            text=message,
            parse_mode='Markdown'
        )
        
        logger.info(f"Like notification sent to {to_user_id} from {from_user_id}")
        
    except Exception as e:
        logger.error(f"Error sending like notification: {e}")

# ========== УЛУЧШЕННЫЙ ИНТЕРФЕЙС ==========

async def create_main_keyboard() -> InlineKeyboardMarkup:
    """Создает основную клавиатуру с главными функциями"""
    keyboard = [
        [InlineKeyboardButton("👀 Смотреть анкеты", callback_data="view_profiles")],
        [InlineKeyboardButton("💞 Мои мэтчи", callback_data="view_matches")],
        [InlineKeyboardButton("📊 Моя статистика", callback_data="my_stats")],
        [InlineKeyboardButton("⚙️ Технические функции", callback_data="tech_functions")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def create_tech_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для технических функций"""
    keyboard = [
        [InlineKeyboardButton("✏️ Редактировать анкету", callback_data="edit_profile")],
        [InlineKeyboardButton("🔄 Сбросить просмотры", callback_data="reset_viewed")],
        [InlineKeyboardButton("🔄 Перезапустить бота", callback_data="restart_bot")],
        [InlineKeyboardButton("📈 Общая статистика", callback_data="global_stats")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str = "Главное меню:"):
    """Показывает главное меню"""
    reply_markup = await create_main_keyboard()
    
    if hasattr(update, 'message') and update.message:
        await update.message.reply_text(message, reply_markup=reply_markup)
    elif hasattr(update, 'callback_query') and update.callback_query:
        try:
            await update.callback_query.edit_message_text(message, reply_markup=reply_markup)
        except BadRequest as e:
            if "Message is not modified" in str(e):
                # Игнорируем ошибку, если сообщение не изменилось
                await update.callback_query.answer()
            else:
                raise

async def show_tech_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает меню технических функций"""
    reply_markup = await create_tech_keyboard()
    
    if hasattr(update, 'callback_query') and update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                "⚙️ Технические функции бота:\n\n"
                "Здесь вы можете управлять настройками и выполнить административные действия",
                reply_markup=reply_markup
            )
        except BadRequest as e:
            if "Message is not modified" in str(e):
                await update.callback_query.answer()
            else:
                raise

# ========== КОМАНДЫ УПРАВЛЕНИЯ ==========

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Справка по командам"""
    help_text = """
🤖 **Доступные команды:**

/start - Начать работу с ботом
/profile - Посмотреть свой профиль
/edit - Редактировать анкету
/stats - Общая статистика бота
/search - Поиск анкет
/restart - Перезапустить бота (сбросить все данные)
/help - Эта справка

💡 **Советы:**
- Используйте кнопки меню для навигации
- Регулярно обновляйте анкету для лучших мэтчей
- Не забывайте проверять раздел "Мои мэтчи"
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Перезапуск бота - сброс данных и начало новой регистрации"""
    try:
        user = update.message.from_user
        user_id = user.id
        
        # Сбрасываем данные пользователя
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
        cursor.execute('DELETE FROM psychologist_profiles WHERE user_id = ?', (user_id,))
        cursor.execute('DELETE FROM client_profiles WHERE user_id = ?', (user_id,))
        cursor.execute('DELETE FROM likes WHERE from_user_id = ? OR to_user_id = ?', (user_id, user_id))
        cursor.execute('DELETE FROM profiles_viewed WHERE user_id = ? OR viewed_user_id = ?', (user_id, user_id))
        
        conn.commit()
        conn.close()
        
        # Очищаем user_data
        context.user_data.clear()
        
        # Отправляем сообщение о перезапуске
        await update.message.reply_text(
            "🔄 Бот перезапущен! Все ваши данные сброшены.\n\n"
            "Давайте начнем заново! Вы психолог или клиент?",
            reply_markup=ReplyKeyboardMarkup(
                [['👨‍⚕️ Психолог', '👤 Клиент']], 
                one_time_keyboard=True, 
                resize_keyboard=True
            )
        )
        
        logger.info(f"User {user_id} restarted bot")
        return ROLE
        
    except Exception as e:
        logger.error(f"Error in restart_command: {e}")
        await update.message.reply_text("Ошибка при перезапуске. Попробуйте /start")
        return ConversationHandler.END

async def edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Редактирование анкеты"""
    try:
        user_id = update.message.from_user.id
        user_data = db.get_user(user_id)
        
        if not user_data:
            await update.message.reply_text("У вас нет анкеты. Используйте /start для создания.")
            return ConversationHandler.END
        
        # Сохраняем текущий профиль в context для предзаполнения
        if user_data['role'] == 'psychologist':
            profile = db.get_psychologist_profile(user_id)
            if profile:
                context.user_data['edit_profile'] = profile
                
                keyboard = [
                    ['👤 Имя', '🎂 Возраст', '👫 Пол'],
                    ['🎓 Образование', '💫 О себе', '🧠 Подход'],
                    ['🎯 Запросы', '💰 Стоимость', '📷 Фото'],
                    ['✅ Завершить редактирование']
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=False, resize_keyboard=True)
                
                await update.message.reply_text(
                    "📝 Редактирование анкеты психолога\n\n"
                    "Выберите, что хотите изменить:",
                    reply_markup=reply_markup
                )
                return EDIT_CHOICE
            else:
                await update.message.reply_text("Профиль не найден. Используйте /start для создания анкеты.")
                return ConversationHandler.END
        else:
            profile = db.get_client_profile(user_id)
            if profile:
                context.user_data['edit_profile'] = profile
                
                keyboard = [
                    ['👤 Имя', '🎂 Возраст', '👫 Пол'],
                    ['🎯 Запрос', '✅ Завершить редактирование']
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=False, resize_keyboard=True)
                
                await update.message.reply_text(
                    "📝 Редактирование анкеты клиента\n\n"
                    "Выберите, что хотите изменить:",
                    reply_markup=reply_markup
                )
                return EDIT_CHOICE
            else:
                await update.message.reply_text("Профиль не найден. Используйте /start для создания анкеты.")
                return ConversationHandler.END
            
    except Exception as e:
        logger.error(f"Error in edit_command: {e}")
        await update.message.reply_text("Ошибка при редактировании анкеты.")
        return ConversationHandler.END

async def edit_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора поля для редактирования"""
    try:
        user_id = update.message.from_user.id
        user_data = db.get_user(user_id)
        choice = update.message.text
        
        if not user_data:
            await update.message.reply_text("Ошибка. Используйте /start")
            return ConversationHandler.END
        
        profile = context.user_data.get('edit_profile', {})
        
        if choice == '✅ Завершить редактирование':
            await update.message.reply_text(
                "✅ Редактирование завершено!",
                reply_markup=ReplyKeyboardRemove()
            )
            await show_main_menu(update, context, "✅ Редактирование завершено!")
            return ConversationHandler.END
        
        elif user_data['role'] == 'psychologist':
            if choice == '👤 Имя':
                await update.message.reply_text(
                    f"Текущее имя: {profile.get('name', 'Не указано')}\n"
                    "Введите новое имя:",
                    reply_markup=ReplyKeyboardRemove()
                )
                return EDIT_PSY_NAME
            elif choice == '🎂 Возраст':
                await update.message.reply_text(
                    f"Текущий возраст: {profile.get('age', 'Не указано')}\n"
                    "Введите новый возраст:",
                    reply_markup=ReplyKeyboardRemove()
                )
                return EDIT_PSY_AGE
            elif choice == '👫 Пол':
                keyboard = [['👨 Мужской', '👩 Женский']]
                reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
                await update.message.reply_text(
                    f"Текущий пол: {profile.get('gender', 'Не указано')}\n"
                    "Выберите новый пол:",
                    reply_markup=reply_markup
                )
                return EDIT_PSY_GENDER
            elif choice == '🎓 Образование':
                await update.message.reply_text(
                    f"Текущее образование: {profile.get('education', 'Не указано')}\n"
                    "Введите новое образование:",
                    reply_markup=ReplyKeyboardRemove()
                )
                return EDIT_PSY_EDUCATION
            elif choice == '💫 О себе':
                await update.message.reply_text(
                    f"Текущее описание: {profile.get('about_me', 'Не указано')}\n"
                    "Введите новое описание:",
                    reply_markup=ReplyKeyboardRemove()
                )
                return EDIT_PSY_ABOUT
            elif choice == '🧠 Подход':
                keyboard = [
                    ['Когнитивно-поведенческая терапия (КПТ)'],
                    ['Психоанализ'],
                    ['Гештальт'],
                    ['Экзистенциально-гуманистическая терапия'],
                    ['3 волна КПТ (АСТ, ДБТ, CFT, MBCT, схема-терапия)'],
                    ['Психодрама'],
                    ['Телесная терапия'],
                    ['Другое']
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
                await update.message.reply_text(
                    f"Текущий подход: {profile.get('approach', 'Не указано')}\n"
                    "Выберите новый подход:",
                    reply_markup=reply_markup
                )
                return EDIT_PSY_APPROACH
            elif choice == '🎯 Запросы':
                await update.message.reply_text(
                    f"Текущие запросы: {profile.get('work_requests', 'Не указано')}\n"
                    "Введите новые запросы:",
                    reply_markup=ReplyKeyboardRemove()
                )
                return EDIT_PSY_REQUESTS
            elif choice == '💰 Стоимость':
                keyboard = [
                    ['Бесплатная первая консультация'],
                    ['1000-2000 руб./сессия'],
                    ['2000-3000 руб./сессия'],
                    ['3000-5000 руб./сессия'],
                    ['Обсуждается индивидуально']
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
                await update.message.reply_text(
                    f"Текущая стоимость: {profile.get('price', 'Не указано')}\n"
                    "Выберите новую стоимость:",
                    reply_markup=reply_markup
                )
                return EDIT_PSY_PRICE
            elif choice == '📷 Фото':
                await update.message.reply_text(
                    "Пришлите новое фото или отправьте /skip чтобы удалить текущее:",
                    reply_markup=ReplyKeyboardRemove()
                )
                return EDIT_PSY_PHOTO
        
        else:  # Клиент
            if choice == '👤 Имя':
                await update.message.reply_text(
                    f"Текущее имя: {profile.get('name', 'Не указано')}\n"
                    "Введите новое имя:",
                    reply_markup=ReplyKeyboardRemove()
                )
                return EDIT_CLIENT_NAME
            elif choice == '🎂 Возраст':
                await update.message.reply_text(
                    f"Текущий возраст: {profile.get('age', 'Не указано')}\n"
                    "Введите новый возраст:",
                    reply_markup=ReplyKeyboardRemove()
                )
                return EDIT_CLIENT_AGE
            elif choice == '👫 Пол':
                keyboard = [['👨 Мужской', '👩 Женский']]
                reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
                await update.message.reply_text(
                    f"Текущий пол: {profile.get('gender', 'Не указано')}\n"
                    "Выберите новый пол:",
                    reply_markup=reply_markup
                )
                return EDIT_CLIENT_GENDER
            elif choice == '🎯 Запрос':
                await update.message.reply_text(
                    f"Текущий запрос: {profile.get('request', 'Не указано')}\n"
                    "Введите новый запрос:",
                    reply_markup=ReplyKeyboardRemove()
                )
                return EDIT_CLIENT_REQUEST
        
        await update.message.reply_text("Неизвестный выбор. Попробуйте снова.")
        return EDIT_CHOICE
        
    except Exception as e:
        logger.error(f"Error in edit_choice: {e}")
        await update.message.reply_text("Ошибка при редактировании.")
        return ConversationHandler.END

# Функции редактирования для психолога
async def edit_psy_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    new_name = update.message.text
    context.user_data['edit_profile']['name'] = new_name
    await update.message.reply_text("✅ Имя обновлено!")
    return await return_to_edit_menu(update, context)

async def edit_psy_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    new_gender = update.message.text
    context.user_data['edit_profile']['gender'] = new_gender
    await update.message.reply_text("✅ Пол обновлен!")
    return await return_to_edit_menu(update, context)

async def edit_psy_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    new_age = update.message.text
    context.user_data['edit_profile']['age'] = new_age
    await update.message.reply_text("✅ Возраст обновлен!")
    return await return_to_edit_menu(update, context)

async def edit_psy_education(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    new_education = update.message.text
    context.user_data['edit_profile']['education'] = new_education
    await update.message.reply_text("✅ Образование обновлено!")
    return await return_to_edit_menu(update, context)

async def edit_psy_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    new_about = update.message.text
    context.user_data['edit_profile']['about_me'] = new_about
    await update.message.reply_text("✅ Описание обновлено!")
    return await return_to_edit_menu(update, context)

async def edit_psy_approach(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    new_approach = update.message.text
    context.user_data['edit_profile']['approach'] = new_approach
    await update.message.reply_text("✅ Подход обновлен!")
    return await return_to_edit_menu(update, context)

async def edit_psy_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    new_requests = update.message.text
    context.user_data['edit_profile']['work_requests'] = new_requests
    await update.message.reply_text("✅ Запросы обновлены!")
    return await return_to_edit_menu(update, context)

async def edit_psy_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    new_price = update.message.text
    context.user_data['edit_profile']['price'] = new_price
    await update.message.reply_text("✅ Стоимость обновлена!")
    return await return_to_edit_menu(update, context)

async def edit_psy_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    if update.message.photo:
        new_photo = update.message.photo[-1].file_id
        context.user_data['edit_profile']['photo_file_id'] = new_photo
        await update.message.reply_text("✅ Фото обновлено!")
    else:
        context.user_data['edit_profile']['photo_file_id'] = None
        await update.message.reply_text("✅ Фото удалено!")
    
    return await return_to_edit_menu(update, context)

# Функции редактирования для клиента
async def edit_client_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    new_name = update.message.text
    context.user_data['edit_profile']['name'] = new_name
    await update.message.reply_text("✅ Имя обновлено!")
    return await return_to_edit_menu(update, context)

async def edit_client_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    new_gender = update.message.text
    context.user_data['edit_profile']['gender'] = new_gender
    await update.message.reply_text("✅ Пол обновлен!")
    return await return_to_edit_menu(update, context)

async def edit_client_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    new_age = update.message.text
    context.user_data['edit_profile']['age'] = new_age
    await update.message.reply_text("✅ Возраст обновлен!")
    return await return_to_edit_menu(update, context)

async def edit_client_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    new_request = update.message.text
    context.user_data['edit_profile']['request'] = new_request
    await update.message.reply_text("✅ Запрос обновлен!")
    return await return_to_edit_menu(update, context)

async def return_to_edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат в меню редактирования с сохранением изменений"""
    user_id = update.message.from_user.id
    user_data = db.get_user(user_id)
    
    # Сохраняем изменения в базу
    profile = context.user_data.get('edit_profile', {})
    if user_data['role'] == 'psychologist':
        db.save_psychologist_profile(
            user_id=user_id,
            name=profile.get('name', ''),
            gender=profile.get('gender', ''),
            age=profile.get('age', ''),
            education=profile.get('education', ''),
            about_me=profile.get('about_me', ''),
            approach=profile.get('approach', ''),
            work_requests=profile.get('work_requests', ''),
            price=profile.get('price', ''),
            photo_file_id=profile.get('photo_file_id')
        )
    else:
        db.save_client_profile(
            user_id=user_id,
            name=profile.get('name', ''),
            gender=profile.get('gender', ''),
            age=profile.get('age', ''),
            request=profile.get('request', '')
        )
    
    # Возвращаемся в меню редактирования
    return await edit_command(update, context)

# ========== ОСНОВНЫЕ ФУНКЦИИ БОТА ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало диалога, выбор роли"""
    try:
        user = update.message.from_user
        user_id = user.id
        username = user.username
        first_name = user.first_name
        last_name = user.last_name
        
        # Обновляем активность пользователя
        db.update_last_active(user_id)
        
        keyboard = [['👨‍⚕️ Психолог', '👤 Клиент']]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(
            'Привет! Я бот для знакомств психологов и клиентов.\n\n'
            'Вы психолог или клиент?',
            reply_markup=reply_markup
        )
        return ROLE
    except Exception as e:
        logger.error(f"Error in start: {e}")
        await update.message.reply_text("Ошибка. Попробуйте /start")
        return ConversationHandler.END

async def role_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора роли"""
    try:
        user = update.message.from_user
        user_id = user.id
        username = user.username
        first_name = user.first_name
        last_name = user.last_name
        choice = update.message.text
        
        if 'Психолог' in choice:
            # Создаем пользователя в базе с сохранением ника
            db.create_user(user_id, username, first_name, last_name, 'psychologist')
            
            await update.message.reply_text(
                '👨‍⚕️ Отлично! Вы психолог. Давайте заполним вашу анкету.\n\n'
                'Как вас зовут? (ФИО или имя):',
                reply_markup=ReplyKeyboardRemove()
            )
            return PSY_NAME
        else:
            # Создаем пользователя в базе с сохранением ника
            db.create_user(user_id, username, first_name, last_name, 'client')
            
            await update.message.reply_text(
                '👤 Отлично! Вы клиент. Давайте заполним вашу анкету.\n\n'
                'Как вас зовут?',
                reply_markup=ReplyKeyboardRemove()
            )
            return CLIENT_NAME
    except Exception as e:
        logger.error(f"Error in role_choice: {e}")
        await update.message.reply_text("Ошибка. Попробуйте /start")
        return ConversationHandler.END

# ========== АНКЕТА ПСИХОЛОГА ==========

async def psy_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Имя психолога"""
    try:
        user_id = update.message.from_user.id
        context.user_data['psy_name'] = update.message.text
        
        # Клавиатура для выбора пола
        gender_keyboard = [['👨 Мужской', '👩 Женский']]
        reply_markup = ReplyKeyboardMarkup(gender_keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(
            'Выберите ваш пол:',
            reply_markup=reply_markup
        )
        return PSY_GENDER
    except Exception as e:
        logger.error(f"Error in psy_name: {e}")
        await update.message.reply_text("Ошибка. Попробуйте /start")
        return ConversationHandler.END

async def psy_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пол психолога"""
    try:
        user_id = update.message.from_user.id
        context.user_data['psy_gender'] = update.message.text
        
        await update.message.reply_text(
            'Укажите ваш возраст:',
            reply_markup=ReplyKeyboardRemove()
        )
        return PSY_AGE
    except Exception as e:
        logger.error(f"Error in psy_gender: {e}")
        await update.message.reply_text("Ошибка. Попробуйте /start")
        return ConversationHandler.END

async def psy_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возраст психолога"""
    try:
        user_id = update.message.from_user.id
        context.user_data['psy_age'] = update.message.text
        
        await update.message.reply_text(
            '🎓 Образование + доп. образование:\n\n'
            'Расскажите о вашем образовании:\n'
            '- Основное психологическое образование\n'
            '- Дополнительные курсы, сертификаты\n'
            '- Повышение квалификации\n\n'
            'Опишите подробно:'
        )
        return PSY_EDUCATION
    except Exception as e:
        logger.error(f"Error in psy_age: {e}")
        await update.message.reply_text("Ошибка. Попробуйте /start")
        return ConversationHandler.END

async def psy_education(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Образование психолога"""
    try:
        user_id = update.message.from_user.id
        context.user_data['psy_education'] = update.message.text
        
        await update.message.reply_text(
            '💫 О себе:\n\n'
            'Опишите свои главные ценности, принципы, которых вы придерживаетесь '
            'в консультировании/жизни.\n\n'
            'Кратко опишите, какой вы человек - ваши идеалы, стремления, '
            'все то, что вы транслируете миру:'
        )
        return PSY_ABOUT
    except Exception as e:
        logger.error(f"Error in psy_education: {e}")
        await update.message.reply_text("Ошибка. Попробуйте /start")
        return ConversationHandler.END

async def psy_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """О себе психолога"""
    try:
        user_id = update.message.from_user.id
        context.user_data['psy_about'] = update.message.text
        
        keyboard = [
            ['Когнитивно-поведенческая терапия (КПТ)'],
            ['Психоанализ'],
            ['Гештальт'],
            ['Экзистенциально-гуманистическая терапия'],
            ['3 волна КПТ (АСТ, ДБТ, CFT, MBCT, схема-терапия)'],
            ['Психодрама'],
            ['Телесная терапия'],
            ['Другое']
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(
            '🧠 Выберите Ваш основной подход:',
            reply_markup=reply_markup
        )
        return PSY_APPROACH
    except Exception as e:
        logger.error(f"Error in psy_about: {e}")
        await update.message.reply_text("Ошибка. Попробуйте /start")
        return ConversationHandler.END

async def psy_approach(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подход психолога"""
    try:
        user_id = update.message.from_user.id
        context.user_data['psy_approach'] = update.message.text
        
        await update.message.reply_text(
            '🎯 Работаю с запросами:\n\n'
            'Напишите, с какими запросами работаете:\n'
            '• тревога\n• поиск себя\n• постановка целей\n• романтические отношения\n'
            '• отношения с семьей\n• одиночество\n• утрата\n• депрессия\n'
            '• неуверенность в себе\n• проблемы с пищевым поведением\n• другое\n\n'
            'Можете перечислить через запятую или написать своими словами:',
            reply_markup=ReplyKeyboardRemove()
        )
        return PSY_REQUESTS
    except Exception as e:
        logger.error(f"Error in psy_approach: {e}")
        await update.message.reply_text("Ошибка. Попробуйте /start")
        return ConversationHandler.END

async def psy_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запросы психолога"""
    try:
        user_id = update.message.from_user.id
        context.user_data['psy_requests'] = update.message.text
        
        keyboard = [
            ['Бесплатная первая консультация'],
            ['1000-2000 руб./сессия'],
            ['2000-3000 руб./сессия'],
            ['3000-5000 руб./сессия'],
            ['Обсуждается индивидуально']
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(
            '💰 Укажите стоимость консультации:',
            reply_markup=reply_markup
        )
        return PSY_PRICE
    except Exception as e:
        logger.error(f"Error in psy_requests: {e}")
        await update.message.reply_text("Ошибка. Попробуйте /start")
        return ConversationHandler.END

async def psy_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Цена психолога"""
    try:
        user_id = update.message.from_user.id
        context.user_data['psy_price'] = update.message.text
        
        await update.message.reply_text(
            '📷 Добавьте фото:\n\n'
            'Пришлите ваше фото для профиля (просто отправьте изображение).\n\n'
            'Если не хотите добавлять фото, отправьте /skip',
            reply_markup=ReplyKeyboardRemove()
        )
        return PSY_PHOTO
    except Exception as e:
        logger.error(f"Error in psy_price: {e}")
        await update.message.reply_text("Ошибка. Попробуйте /start")
        return ConversationHandler.END

async def psy_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Фото психолога"""
    try:
        user_id = update.message.from_user.id
        
        photo_file_id = None
        if update.message.photo:
            photo_file_id = update.message.photo[-1].file_id
            photo_text = "✅ Фото добавлено!"
        else:
            photo_text = "❌ Фото не добавлено"
        
        # Сохраняем профиль в базу данных
        db.save_psychologist_profile(
            user_id=user_id,
            name=context.user_data['psy_name'],
            gender=context.user_data['psy_gender'],
            age=context.user_data['psy_age'],
            education=context.user_data['psy_education'],
            about_me=context.user_data['psy_about'],
            approach=context.user_data['psy_approach'],
            work_requests=context.user_data['psy_requests'],
            price=context.user_data['psy_price'],
            photo_file_id=photo_file_id
        )
        
        profile = f"""
✅ Анкета заполнена!

👤{context.user_data['psy_name']}, пол: {context.user_data['psy_gender']},{context.user_data['psy_age']}

🎓 Образование: {context.user_data['psy_education']}

💫 О себе:{context.user_data['psy_about']}

🧠 Подход:{context.user_data['psy_approach']}

🎯 Работаю с запросами: {context.user_data['psy_requests']}

💰 Стоимость: {context.user_data['psy_price']}

{photo_text}
        """
        
        await update.message.reply_text(profile)
        
        if photo_file_id:
            await update.message.reply_photo(photo=photo_file_id)
        
        # Показываем главное меню после завершения анкеты
        await show_main_menu(update, context, "🎉 Регистрация завершена! Теперь вы можете пользоваться ботом:")
        
        logger.info(f"Психолог {user_id} заполнил анкету")
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error in psy_photo: {e}")
        await update.message.reply_text("Ошибка. Попробуйте /start")
        return ConversationHandler.END

async def psy_skip_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пропуск фото психолога"""
    try:
        user_id = update.message.from_user.id
        
        # Сохраняем профиль в базу данных
        db.save_psychologist_profile(
            user_id=user_id,
            name=context.user_data['psy_name'],
            gender=context.user_data['psy_gender'],
            age=context.user_data['psy_age'],
            education=context.user_data['psy_education'],
            about_me=context.user_data['psy_about'],
            approach=context.user_data['psy_approach'],
            work_requests=context.user_data['psy_requests'],
            price=context.user_data['psy_price'],
            photo_file_id=None
        )
        
        profile = f"""
✅ Анкета заполнена!

👤 {context.user_data['psy_name']}, пол:{context.user_data['psy_gender']}, {context.user_data['psy_age']}

🎓 Образование: {context.user_data['psy_education']}

💫 О себе: {context.user_data['psy_about']}

🧠 Подход: {context.user_data['psy_approach']}

🎯 Работаю с запросами: {context.user_data['psy_requests']}

💰 Стоимость: {context.user_data['psy_price']}

❌ Фото не добавлено
        """
        
        await update.message.reply_text(profile)
        
        # Показываем главное меню после завершения анкеты
        await show_main_menu(update, context, "🎉 Регистрация завершена! Теперь вы можете пользоваться ботом:")
        
        logger.info(f"Психолог {user_id} заполнил анкету без фото")
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error in psy_skip_photo: {e}")
        await update.message.reply_text("Ошибка. Попробуйте /start")
        return ConversationHandler.END

# ========== АНКЕТА КЛИЕНТА ==========

async def client_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Имя клиента"""
    try:
        user_id = update.message.from_user.id
        context.user_data['client_name'] = update.message.text
        
        # Клавиатура для выбора пола клиента
        gender_keyboard = [['👨 Мужской', '👩 Женский']]
        reply_markup = ReplyKeyboardMarkup(gender_keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(
            'Выберите ваш пол:',
            reply_markup=reply_markup
        )
        return CLIENT_GENDER
    except Exception as e:
        logger.error(f"Error in client_name: {e}")
        await update.message.reply_text("Ошибка. Попробуйте /start")
        return ConversationHandler.END

async def client_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пол клиента"""
    try:
        user_id = update.message.from_user.id
        context.user_data['client_gender'] = update.message.text
        
        await update.message.reply_text(
            'Укажите ваш возраст:',
            reply_markup=ReplyKeyboardRemove()
        )
        return CLIENT_AGE
    except Exception as e:
        logger.error(f"Error in client_gender: {e}")
        await update.message.reply_text("Ошибка. Попробуйте /start")
        return ConversationHandler.END

async def client_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возраст клиента"""
    try:
        user_id = update.message.from_user.id
        context.user_data['client_age'] = update.message.text
        
        await update.message.reply_text(
            '🎯 Опишите ваш запрос к психологу:\n'
            'Например: "тревога", "поиск себя", "отношения", "одиночество" и т.д.'
        )
        return CLIENT_REQUEST
    except Exception as e:
        logger.error(f"Error in client_age: {e}")
        await update.message.reply_text("Ошибка. Попробуйте /start")
        return ConversationHandler.END

async def client_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запрос клиента"""
    try:
        user_id = update.message.from_user.id
        context.user_data['client_request'] = update.message.text
        
        # Сохраняем профиль в базу данных
        db.save_client_profile(
            user_id=user_id,
            name=context.user_data['client_name'],
            gender=context.user_data['client_gender'],
            age=context.user_data['client_age'],
            request=context.user_data['client_request']
        )
        
        profile = f"""
✅ Ваш профиль клиента заполнен!

👤 Имя: {context.user_data['client_name']}, Пол: {context.user_data['client_gender']}, Возраст: {context.user_data['client_age']}
🎯 Ваш запрос: {context.user_data['client_request']}
        """
        
        await update.message.reply_text(profile)
        
        # Показываем главное меню после завершения анкеты
        await show_main_menu(update, context, "🎉 Регистрация завершена! Теперь вы можете пользоваться ботом:")
        
        logger.info(f"Клиент {user_id} заполнил анкету")
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error in client_request: {e}")
        await update.message.reply_text("Ошибка. Попробуйте /start")
        return ConversationHandler.END

# ========== СИСТЕМА ЛАЙКОВ И ПРОСМОТРА ==========

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки - УЛУЧШЕННАЯ ВЕРСИЯ"""
    try:
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        
        if query.data == "view_profiles":
            await show_next_profile(update, context, user_id)
        
        elif query.data == "my_stats":
            await show_stats(update, context, user_id)
        
        elif query.data == "view_matches":
            await show_matches(update, context, user_id)
        
        elif query.data == "tech_functions":
            await show_tech_menu(update, context)
        
        elif query.data == "back_to_main":
            await show_main_menu(update, context)
        
        elif query.data == "edit_profile":
            await edit_from_button(update, context, user_id)
        
        elif query.data == "restart_bot":
            await restart_from_button(update, context, user_id)
        
        elif query.data == "global_stats":
            await show_global_stats(update, context, user_id)
        
        elif query.data == "reset_viewed":
            await reset_viewed_profiles(update, context, user_id)
        
        elif query.data.startswith("like_"):
            target_id = int(query.data.split("_")[1])
            await like_profile(update, context, user_id, target_id)
        
        elif query.data.startswith("skip_"):
            await show_next_profile(update, context, user_id)
        
        else:
            logger.warning(f"Unknown button data: {query.data}")
            await query.edit_message_text("Неизвестная команда. Используйте /start")
            
    except Exception as e:
        logger.error(f"Error in button_handler: {e}")
        try:
            await update.callback_query.edit_message_text(
                "Произошла ошибка при обработке команды. Попробуйте еще раз или используйте /start",
                reply_markup=await create_main_keyboard()
            )
        except:
            # Если не удалось редактировать сообщение, отправляем новое
            await context.bot.send_message(
                chat_id=user_id,
                text="Произошла ошибка при обработке команды. Попробуйте еще раз или используйте /start",
                reply_markup=await create_main_keyboard()
            )

async def edit_from_button(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Редактирование анкеты из кнопки - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
    try:
        query = update.callback_query
        await query.answer()
        
        user_data = db.get_user(user_id)
        
        if not user_data:
            await query.edit_message_text("У вас нет анкеты. Используйте /start для создания.")
            return
        
        # Отправляем новое сообщение вместо редактирования текущего
        if user_data['role'] == 'psychologist':
            profile = db.get_psychologist_profile(user_id)
            if profile:
                context.user_data['edit_profile'] = profile
                
                keyboard = [
                    ['👤 Имя', '🎂 Возраст', '👫 Пол'],
                    ['🎓 Образование', '💫 О себе', '🧠 Подход'],
                    ['🎯 Запросы', '💰 Стоимость', '📷 Фото'],
                    ['✅ Завершить редактирование']
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=False, resize_keyboard=True)
                
                # Отправляем новое сообщение с обычной клавиатурой
                await context.bot.send_message(
                    chat_id=user_id,
                    text="📝 Редактирование анкеты психолога\n\n"
                         "Выберите, что хотите изменить:",
                    reply_markup=reply_markup
                )
                return EDIT_CHOICE
            else:
                await query.edit_message_text("Профиль не найден. Используйте /start для создания анкеты.")
                return ConversationHandler.END
        else:
            profile = db.get_client_profile(user_id)
            if profile:
                context.user_data['edit_profile'] = profile
                
                keyboard = [
                    ['👤 Имя', '🎂 Возраст', '👫 Пол'],
                    ['🎯 Запрос', '✅ Завершить редактирование']
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=False, resize_keyboard=True)
                
                # Отправляем новое сообщение с обычной клавиатурой
                await context.bot.send_message(
                    chat_id=user_id,
                    text="📝 Редактирование анкеты клиента\n\n"
                         "Выберите, что хотите изменить:",
                    reply_markup=reply_markup
                )
                return EDIT_CHOICE
            else:
                await query.edit_message_text("Профиль не найден. Используйте /start для создания анкеты.")
                return ConversationHandler.END
            
    except Exception as e:
        logger.error(f"Error in edit_from_button: {e}")
        await update.callback_query.edit_message_text("Ошибка при редактировании анкеты.")
        return ConversationHandler.END

async def restart_from_button(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Перезапуск бота из кнопки - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
    try:
        query = update.callback_query
        await query.answer()
        
        # Сбрасываем данные пользователя
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
        cursor.execute('DELETE FROM psychologist_profiles WHERE user_id = ?', (user_id,))
        cursor.execute('DELETE FROM client_profiles WHERE user_id = ?', (user_id,))
        cursor.execute('DELETE FROM likes WHERE from_user_id = ? OR to_user_id = ?', (user_id, user_id))
        cursor.execute('DELETE FROM profiles_viewed WHERE user_id = ? OR viewed_user_id = ?', (user_id, user_id))
        
        conn.commit()
        conn.close()
        
        # Очищаем user_data
        context.user_data.clear()
        
        # Отправляем сообщение о перезапуске
        keyboard = [['👨‍⚕️ Психолог', '👤 Клиент']]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await query.edit_message_text(
            "🔄 Бот перезапущен! Все ваши данные сброшены.\n\n"
            "Давайте начнем заново! Вы психолог или клиент?",
            reply_markup=reply_markup
        )
        
        logger.info(f"User {user_id} restarted bot from button")
        return ROLE
        
    except Exception as e:
        logger.error(f"Error in restart_from_button: {e}")
        await update.callback_query.edit_message_text("Ошибка при перезапуске. Попробуйте /start")
        return ConversationHandler.END

async def show_global_stats(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Показать общую статистику бота"""
    try:
        stats = db.get_statistics()
        stats_text = f"""
📈 Общая статистика бота:

👨‍⚕️ Психологов: {stats['psychologists_count']}
👤 Клиентов: {stats['clients_count']}
❤️ Всего лайков: {stats['total_likes']}
💝 Взаимных мэтчей: {stats['mutual_matches']}
        """
        await update.callback_query.edit_message_text(stats_text, reply_markup=await create_tech_keyboard())
    except Exception as e:
        logger.error(f"Error in show_global_stats: {e}")
        await update.callback_query.edit_message_text("Ошибка при загрузке статистики")

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Показать статистику пользователя"""
    try:
        user_data = db.get_user(user_id)
        if not user_data:
            await update.callback_query.edit_message_text("Сначала заполните анкету через /start")
            return
        
        user_likes = db.get_user_likes(user_id)
        mutual_likes = db.get_mutual_likes(user_id)
        
        if user_data['role'] == 'psychologist':
            role_text = "психолог"
            target_role = "клиентов"
        else:
            role_text = "клиент" 
            target_role = "психологов"
        
        stats_text = f"""
📊 Ваша статистика:

👤 Ваш профиль: {role_text}
❤️ Вы лайкнули: {len(user_likes)} {target_role}
💝 Взаимные лайки: {len(mutual_likes)} {target_role}
        """
        
        await update.callback_query.edit_message_text(stats_text, reply_markup=await create_main_keyboard())
            
    except Exception as e:
        logger.error(f"Error in show_stats: {e}")
        await update.callback_query.edit_message_text("Ошибка при загрузке статистики")

async def reset_viewed_profiles(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Сброс просмотренных профилей"""
    try:
        db.reset_viewed_profiles(user_id)
        
        await update.callback_query.edit_message_text(
            "✅ Список просмотренных анкет очищен! Теперь вы снова увидите все анкеты.",
            reply_markup=await create_tech_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Error in reset_viewed_profiles: {e}")
        await update.callback_query.edit_message_text("Ошибка при сбросе просмотренных анкет")

async def show_next_profile(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Показать следующую анкету - УЛУЧШЕННАЯ ВЕРСИЯ С ОБРАБОТКОЙ ОШИБОК"""
    try:
        current_user = db.get_user(user_id)
        if not current_user:
            await update.callback_query.edit_message_text(
                "❌ Ваш профиль не найден. Используйте /start для создания анкеты.",
                reply_markup=await create_main_keyboard()
            )
            return
        
        # Определяем какие анкеты показывать
        if current_user['role'] == 'psychologist':
            # Психологам показываем клиентов
            target_users = db.get_all_clients()
        else:
            # Клиентам показываем психологов
            target_users = db.get_all_psychologists()
        
        # Исключаем уже просмотренные и лайкнутые
        viewed = db.get_viewed_profiles(user_id)
        user_likes = db.get_user_likes(user_id)
        
        available_users = [user for user in target_users 
                          if user['user_id'] != user_id 
                          and user['user_id'] not in viewed 
                          and user['user_id'] not in user_likes]
        
        if not available_users:
            # УЛУЧШЕННАЯ ОБРАБОТКА: нет доступных анкет
            await update.callback_query.edit_message_text(
                "🎉 Вы просмотрели все анкеты!\n\n"
                "Больше нет новых анкет для просмотра. "
                "Вы можете сбросить список просмотренных анкет в технических функциях "
                "или подождать пока появятся новые пользователи.",
                reply_markup=await create_main_keyboard()
            )
            return
        
        # Берем первую доступную анкету
        target_user = available_users[0]
        
        # Формируем анкету для показа
        if current_user['role'] == 'client':  # Клиентам показываем психологов
            profile_text = f"""
👨‍⚕️ Анкета психолога:

👤 {target_user.get('name', 'Не указано')}, {target_user.get('gender', 'Не указано')}, {target_user.get('age', 'Не указано')}
🎓 Образование: {target_user.get('education', 'Не указано')}
💫 О себе: {target_user.get('about_me', 'Не указано')}
🧠 Подход: {target_user.get('approach', 'Не указано')}
🎯 Работает с: {target_user.get('work_requests', 'Не указано')}
💰 Стоимость: {target_user.get('price', 'Не указано')}
            """
        else:  # Психологам показываем клиентов
            profile_text = f"""
👤 Анкета клиента:

👤 {target_user.get('name', 'Не указано')}, {target_user.get('gender', 'Не указано')}, {target_user.get('age', 'Не указано')}
🎯 Запрос: {target_user.get('request', 'Не указано')}
            """
        
        # Клавиатура с действиями
        keyboard = [
            [
                InlineKeyboardButton("❤️ Лайк", callback_data=f"like_{target_user['user_id']}"),
                InlineKeyboardButton("➡️ Дальше", callback_data=f"skip_{target_user['user_id']}")
            ],
            [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Отправляем новое сообщение вместо редактирования
        if target_user.get('photo_file_id'):
            # Сначала отправляем фото как отдельное сообщение
            await update.callback_query.message.reply_photo(
                photo=target_user['photo_file_id']
            )
            # Затем отправляем текстовое сообщение с анкетой и кнопками
            await update.callback_query.message.reply_text(
                profile_text,
                reply_markup=reply_markup
            )
        else:
            # Если фото нет, редактируем текущее сообщение с обработкой ошибок
            try:
                await update.callback_query.edit_message_text(
                    profile_text,
                    reply_markup=reply_markup
                )
            except BadRequest as e:
                if "Message is not modified" in str(e):
                    # Игнорируем ошибку, если сообщение не изменилось
                    await update.callback_query.answer()
                else:
                    raise
        
        # Добавляем в просмотренные
        db.add_viewed_profile(user_id, target_user['user_id'])
        
    except Exception as e:
        logger.error(f"Error in show_next_profile: {e}")
        await update.callback_query.edit_message_text(
            "Произошла ошибка при загрузке анкеты. Попробуйте еще раз.",
            reply_markup=await create_main_keyboard()
        )

async def like_profile(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, target_id: int):
    """Обработка лайка - ИСПРАВЛЕННАЯ ВЕРСИЯ БЕЗ ДУБЛИРОВАНИЯ"""
    try:
        success, is_mutual = db.create_like(user_id, target_id)
        
        if not success:
            # Отправляем новое сообщение вместо редактирования
            await update.callback_query.message.reply_text("Вы уже лайкали этого пользователя")
            return
        
        # Получаем информацию о пользователе, которого лайкнули
        target_user = db.get_user(target_id)
        target_profile = None
        
        if target_user['role'] == 'psychologist':
            target_profile = db.get_psychologist_profile(target_id)
        else:
            target_profile = db.get_client_profile(target_id)
        
        target_name = target_profile.get('name', 'пользователь') if target_profile else 'пользователь'
        target_username = target_user.get('username')
        
        if is_mutual:
            # ВЗАИМНЫЙ ЛАЙК - отправляем уведомления ОДИН РАЗ каждому пользователю
            
            # Получаем информацию о текущем пользователе для уведомления второму
            current_user = db.get_user(user_id)
            current_profile = None
            
            if current_user['role'] == 'psychologist':
                current_profile = db.get_psychologist_profile(user_id)
            else:
                current_profile = db.get_client_profile(user_id)
            
            current_name = current_profile.get('name', 'пользователь') if current_profile else 'пользователь'
            current_username = current_user.get('username')

            # Формируем сообщение для текущего пользователя
            if target_username:
                current_user_msg = (
                    f"💞 У вас взаимный лайк с {target_name}!\n\n"
                    f"👤 Username: @{target_username}\n"
                    "💌 Можете написать друг другу и начать общение!"
                )
            else:
                current_user_msg = (
                    f"💞 У вас взаимный лайк с {target_name}!\n\n"
                    f"👤 Имя: {target_name}\n"
                    "❌ К сожалению, у этого пользователя не указан username.\n"
                    "Вы можете связаться через другие контакты, если они указаны в анкете."
                )

            # Формируем сообщение для целевого пользователя
            if current_username:
                target_user_msg = (
                    f"💞 У вас взаимный лайк с {current_name}!\n\n"
                    f"👤 Username: @{current_username}\n"
                    "💌 Можете написать друг другу и начать общение!"
                )
            else:
                target_user_msg = (
                    f"💞 У вас взаимный лайк с {current_name}!\n\n"
                    f"👤 Имя: {current_name}\n"
                    "❌ К сожалению, у пользователя не указан username.\n"
                    "Вы можете связаться через другие контакты, если они указаны в анкете."
                )

            # Отправляем уведомление текущему пользователю
            await context.bot.send_message(chat_id=user_id, text=current_user_msg)
            # Отправляем уведомление целевому пользователю
            await context.bot.send_message(chat_id=target_id, text=target_user_msg)
            
        else:
            # Если лайк не взаимный, просто уведомляем текущего пользователя
            await update.callback_query.message.reply_text(
                f"❤️ Вы поставили лайк {target_name}! Ждем ответной реакции."
            )
            
            # И отправляем уведомление о лайке целевому пользователю
            await send_like_notification(context, user_id, target_id)
        
        # Показываем следующую анкету через 1 секунду
        import asyncio
        await asyncio.sleep(1)
        await show_next_profile(update, context, user_id)
        
    except Exception as e:
        logger.error(f"Error in like_profile: {e}")
        await update.callback_query.message.reply_text("Ошибка при обработке лайка")

async def show_matches(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Показать мэтчи пользователя"""
    try:
        mutual_likes = db.get_mutual_likes(user_id)
        
        if not mutual_likes:
            await update.callback_query.edit_message_text(
                "У вас пока нет взаимных лайков 😔\n\n"
                "Продолжайте смотреть анкеты и ставить лайки!",
                reply_markup=await create_main_keyboard()
            )
            return
        
        matches_text = "💞 Ваши взаимные лайки:\n\n"
        
        for match in mutual_likes:
            username = match.get('username')
            name = match.get('name', 'Не указано')
            role = "психолог" if match.get('role') == 'psychologist' else "клиент"
            
            if username:
                matches_text += f"👤 {name} (@{username}) - {role}\n"
            else:
                matches_text += f"👤 {name} (нет username) - {role}\n"
        
        await update.callback_query.edit_message_text(matches_text, reply_markup=await create_main_keyboard())
        
    except Exception as e:
        logger.error(f"Error in show_matches: {e}")
        await update.callback_query.edit_message_text("Ошибка при загрузке мэтчей")

# ========== ОБЩИЕ ФУНКЦИИ ==========

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена диалога"""
    await update.message.reply_text(
        'Анкета отменена. Используйте /start чтобы начать заново.',
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать профиль пользователя"""
    try:
        user_id = update.message.from_user.id
        user_data = db.get_user(user_id)
        
        if not user_data:
            await update.message.reply_text('У вас нет заполненного профиля. Используйте /start')
            return
        
        if user_data['role'] == 'psychologist':
            profile = db.get_psychologist_profile(user_id)
            if profile:
                text = f"""
👨‍⚕️ Ваш профиль психолога:

👤 Имя: {profile.get('name', 'Не указано')}
🎂 Возраст: {profile.get('age', 'Не указано')}
🧠 Подход: {profile.get('approach', 'Не указано')}
💰 Стоимость: {profile.get('price', 'Не указано')}
                """
                
                if profile.get('photo_file_id'):
                    await update.message.reply_photo(
                        photo=profile['photo_file_id']
                    )
            else:
                text = "Профиль психолога не найден"
        else:
            profile = db.get_client_profile(user_id)
            if profile:
                text = f"""
👤 Ваш профиль клиента:

👤 Имя: {profile.get('name', 'Не указано')}
🎂 Возраст: {profile.get('age', 'Не указано')}
🎯 Запрос: {profile.get('request', 'Не указано')}
                """
            else:
                text = "Профиль клиента не найден"
        
        await update.message.reply_text(text)
            
    except Exception as e:
        logger.error(f"Error in show_profile: {e}")
        await update.message.reply_text("Произошла ошибка.")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать общую статистику"""
    try:
        stats = db.get_statistics()
        stats_text = f"""
📈 Общая статистика бота:

👨‍⚕️ Психологов: {stats['psychologists_count']}
👤 Клиентов: {stats['clients_count']}
❤️ Всего лайков: {stats['total_likes']}
💝 Взаимных мэтчей: {stats['mutual_matches']}
        """
        await update.message.reply_text(stats_text)
    except Exception as e:
        logger.error(f"Error in stats_command: {e}")
        await update.message.reply_text("Ошибка при загрузке статистики")

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для поиска анкет"""
    await show_main_menu(update, context, "🔍 Начните просмотр анкет:")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ошибок"""
    logger.error(f"Exception while handling an update: {context.error}")

def main():
    try:
        # Проверяем токен
        if not BOT_TOKEN:
            print("❌ ОШИБКА: BOT_TOKEN не найден!")
            print("💡 Решение: Добавьте BOT_TOKEN в Secrets Replit")
            print("🔄 Перезапуск через 10 секунд...")
            import time
            time.sleep(10)
            main()
            return
        
        # Создаем приложение
        app = Application.builder().token(BOT_TOKEN).build()
        
        # Добавляем обработчики ошибок
        app.add_error_handler(error_handler)
        
        # Основной ConversationHandler для создания анкеты
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', start)],
            states={
                # Общее состояние выбора роли
                ROLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, role_choice)],
                
                # Состояния для психолога
                PSY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, psy_name)],
                PSY_GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, psy_gender)],
                PSY_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, psy_age)],
                PSY_EDUCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, psy_education)],
                PSY_ABOUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, psy_about)],
                PSY_APPROACH: [MessageHandler(filters.TEXT & ~filters.COMMAND, psy_approach)],
                PSY_REQUESTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, psy_requests)],
                PSY_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, psy_price)],
                PSY_PHOTO: [
                    MessageHandler(filters.PHOTO, psy_photo),
                    CommandHandler('skip', psy_skip_photo)
                ],
                
                # Состояния для клиента
                CLIENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_name)],
                CLIENT_GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_gender)],
                CLIENT_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_age)],
                CLIENT_REQUEST: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_request)],
            },
            fallbacks=[CommandHandler('cancel', cancel)]
        )
        
        # ConversationHandler для редактирования анкеты
        edit_conv_handler = ConversationHandler(
            entry_points=[CommandHandler('edit', edit_command)],
            states={
                EDIT_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_choice)],
                
                # Редактирование для психолога
                EDIT_PSY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_psy_name)],
                EDIT_PSY_GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_psy_gender)],
                EDIT_PSY_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_psy_age)],
                EDIT_PSY_EDUCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_psy_education)],
                EDIT_PSY_ABOUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_psy_about)],
                EDIT_PSY_APPROACH: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_psy_approach)],
                EDIT_PSY_REQUESTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_psy_requests)],
                EDIT_PSY_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_psy_price)],
                EDIT_PSY_PHOTO: [
                    MessageHandler(filters.PHOTO, edit_psy_photo),
                    CommandHandler('skip', edit_psy_photo)
                ],
                
                # Редактирование для клиента
                EDIT_CLIENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_client_name)],
                EDIT_CLIENT_GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_client_gender)],
                EDIT_CLIENT_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_client_age)],
                EDIT_CLIENT_REQUEST: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_client_request)],
            },
            fallbacks=[CommandHandler('cancel', cancel)]
        )
        
        # Добавляем все обработчики
        app.add_handler(conv_handler)
        app.add_handler(edit_conv_handler)
        app.add_handler(CommandHandler('profile', show_profile))
        app.add_handler(CommandHandler('stats', stats_command))
        app.add_handler(CommandHandler('search', search_command))
        app.add_handler(CommandHandler('restart', restart_command))
        app.add_handler(CommandHandler('help', help_command))
        app.add_handler(CallbackQueryHandler(button_handler))
        
        print("=" * 50)
        print("🤖 Бот запускается на Replit...")
        print("📞 Токен:", "✅ Установлен" if BOT_TOKEN else "❌ Отсутствует")
        print("🕒 Время:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        print("=" * 50)
        
        # Запускаем бота
        app.run_polling(
            poll_interval=3,
            drop_pending_updates=True,
            timeout=60
        )
        
    except Exception as e:
        logger.error(f"Ошибка запуска бота: {e}")
        print(f"🔴 Критическая ошибка: {e}")
        print("🔄 Перезапуск через 10 секунд...")
        import time
        time.sleep(10)
        main()  # Рекурсивный перезапуск

if __name__ == '__main__':
    main()