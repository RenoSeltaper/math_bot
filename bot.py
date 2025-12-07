# bot.py
# Telegram-бот для приёма заявок репетитора (математика 3-9 классы)
# Aiogram 3.x
# Вставь свой TOKEN и ADMIN_ID ниже!

import asyncio
import logging
import re
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Text
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

logging.basicConfig(level=logging.INFO)

# ---- ВАЖНО: Вставь сюда свой токен и числовой ADMIN_ID (твой telegram id) ----
TOKEN = "ВАШ_BOT_TOKEN_HERE"
ADMIN_ID = 1091446917  # <-- замени на свой числовой ID
# ---------------------------------------------------------------------------

# Ссылка преподавателя, которая будет выдаваться пользователю после подтверждения
TEACHER_TG_LINK = "https://t.me/mathseltaper"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- Временное хранилище заявок/сессий (в памяти). Для продакшна — БД. ---
user_data = {}  # ключ: user_id, значение: dict

# --- Главное меню (reply keyboard) ---
def main_menu():
    kb = ReplyKeyboardBuilder()
    kb.button(text="?? Запись на занятия")
    kb.button(text="?? Стоимость")
    kb.button(text="?? Наш ТГК")
    kb.adjust(1, 2, 2)
    return kb.as_markup(resize_keyboard=True)

# --- Клавиатура со списком услуг (везде одна и та же, но можно фильтровать по классу при желании) ---
def services_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="Подготовка к ОГЭ (9 класс) — 1 000 ?", callback_data="srv_oge")
    kb.button(text="Школьный курс + Подготовка к ОГЭ — 1 200 ?", callback_data="srv_oge_school")
    kb.button(text="Школьный курс + Подготовка к ВПР (7-8 классы) — 1 000 ?", callback_data="srv_vpr_78")
    kb.button(text="Школьный курс + Подготовка к ВПР (4-6 классы) — 700 ?", callback_data="srv_vpr_46")
    kb.button(text="Подготовка к ВПР — 700 ?", callback_data="srv_vpr")
    kb.adjust(1)
    return kb.as_markup()

# --- Кнопка подтверждения для админа в сообщении заявки ---
def admin_confirm_keyboard(applicant_user_id: int, service_code: str):
    # callback_data: confirm_{user_id}_{service_code}
    kb = InlineKeyboardBuilder()
    kb.button(
        text="Подтвердить ученика",
        callback_data=f"confirm_{applicant_user_id}_{service_code}"
    )
    kb.adjust(1)
    return kb.as_markup()

# --- Кнопка для пользователя с ссылкой на преподавателя ---
def send_contact_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="Написать преподавателю", url=TEACHER_TG_LINK)
    kb.adjust(1)
    return kb.as_markup()

# --- Обработчик /start ---
@dp.message(CommandStart())
async def start_handler(message: types.Message):
    await message.answer(
        "Привет! ??\nЯ помогу тебе записаться на занятия по математике (3–9 класс).\nВыбирай раздел:",
        reply_markup=main_menu()
    )

# --- Наш ТГК ---
@dp.message(Text(equals="?? Наш ТГК"))
async def tgk_handler(message: types.Message):
    await message.answer(f"Наш телеграм-канал / ссылка на тг-контент:\n{TEACHER_TG_LINK}")

# --- Стоимость (выводим список услуг/цен) ---
@dp.message(Text(equals="?? Стоимость"))
async def cost_handler(message: types.Message):
    text = (
        "?? *Стоимость обучения:*\n\n"
        "• Подготовка к ОГЭ (9 класс) — *1 000 ?*\n"
        "• Школьный курс + Подготовка к ОГЭ — *1 200 ?*\n"
        "• Школьный курс + Подготовка к ВПР (7–8 классы) — *1 000 ?*\n"
        "• Школьный курс + Подготовка к ВПР (4–6 классы) — *700 ?*\n"
        "• Подготовка к ВПР — *700 ?*\n\n"
        "Если хотите записаться — нажмите «?? Запись на занятия»."
    )
    await message.answer(text, parse_mode="Markdown")

# --- Запись на занятия: показываем шаблон анкеты ---
@dp.message(Text(equals="?? Запись на занятия"))
async def record_handler(message: types.Message):
    await message.answer(
        "Отлично! Тебе нужно заполнить анкетку по следующему шаблону:\n\n"
        "Имя :\n"
        "Фамилия :\n"
        "Возраст :\n"
        "Класс :\n\n"
        "Отправь, пожалуйста, именно в таком формате (или просто пришли эти строки)."
    )
    # отмечаем, что ждём форму от этого пользователя
    user_data[message.from_user.id] = {"waiting": "form"}

# --- Универсальный обработчик текстовых сообщений (анкет и пр.) ---
@dp.message()
async def general_text_handler(message: types.Message):
    uid = message.from_user.id
    text = message.text.strip()

    # Если ожидается анкета
    if uid in user_data and user_data[uid].get("waiting") == "form":
        # Сохраняем текст анкеты
        user_data[uid]["form_raw"] = text
        user_data[uid]["waiting"] = None

        # Попытка извлечь поле "Класс" из анкеты
        class_value = extract_class_from_form(text)
        user_data[uid]["class"] = class_value  # может быть None

        # Сообщаем и предлагаем выбрать услугу
        if class_value:
            await message.answer(
                f"Анкета получена. Похоже, вы указали Класс: *{class_value}*.\n\n"
                "Теперь выберите, что вам нужно:",
                parse_mode="Markdown",
                reply_markup=services_keyboard()
            )
        else:
            # Если не нашли класс — всё равно показываем услуги, но просим указать класс отдельно
            await message.answer(
                "Анкета получена, но не удалось автоматически определить поле «Класс». "
                "Если хотите, отправьте сейчас просто номер класса (например, 5 или 9), "
                "или выберите услугу сразу — можно указать класс позже.",
                reply_markup=services_keyboard()
            )
        return

    # Если пришло сообщение, когда не ожидали форму — можно игнорировать или подсказать
    # Мы не мешаем: просто напоминаем про главное меню
    if text.lower() in ("/help", "help"):
        await message.answer("Напиши '?? Запись на занятия', '?? Стоимость' или '?? Наш ТГК'.", reply_markup=main_menu())
    else:
        # Не реагируем навязчиво — оставим пользователю меню
        await message.answer("Выбери пункт из меню или напиши '?? Запись на занятия' чтобы заполнить анкету.", reply_markup=main_menu())

# --- Вспомогательная функция: извлечь значение Класс: ... из текста анкеты ---
def extract_class_from_form(text: str) -> str | None:
    """
    Пытаемся найти строку, начинающуюся с 'Класс' (в разных вариантах), и вернуть значение.
    Примеры:
      "Класс : 7"
      "Класс: 9 класс"
      "класс - 8"
    """
    # Обычный поиск по строкам
    for line in text.splitlines():
        if re.search(r'\bкласс\b', line, flags=re.IGNORECASE):
            # убираем 'Класс', ':' и т.п.
            val = re.sub(r'(?i)\bкласс\b', '', line).replace(':', '').replace('-', '').strip()
            if val:
                return val
    # Попытка найти просто число 1-11 на отдельной строке
    for line in text.splitlines():
        line_clean = line.strip()
        if re.fullmatch(r'[1-9]|10|11', line_clean):
            return line_clean
    return None

# --- Обработчик выбора услуги (callback_query со srv_) ---
@dp.callback_query(lambda c: c.data and c.data.startswith("srv_"))
async def choose_service_callback(callback: types.CallbackQuery):
    uid = callback.from_user.id
    svc = callback.data  # например 'srv_oge'
    service_map = {
        "srv_oge": "Подготовка к ОГЭ (9 класс) — 1 000 ?",
        "srv_oge_school": "Школьный курс + Подготовка к ОГЭ — 1 200 ?",
        "srv_vpr_78": "Школьный курс + Подготовка к ВПР (7-8 классы) — 1 000 ?",
        "srv_vpr_46": "Школьный курс + Подготовка к ВПР (4-6 классы) — 700 ?",
        "srv_vpr": "Подготовка к ВПР — 700 ?",
    }
    service_text = service_map.get(svc, "Выбранная услуга")

    # Получаем анкеты пользователя (если была)
    form_text = user_data.get(uid, {}).get("form_raw", "Анкета не предоставлена.")
    class_value = user_data.get(uid, {}).get("class", "не указан")

    # Оповещаем пользователя
    await callback.message.answer("Отлично! Заявка отправлена преподавателю ??")

    # Отправляем администратору (тебе) заявку с кнопкой подтверждения
    admin_message = (
        f"?? *Новая заявка!*\n\n"
        f"*Пользователь:* [{callback.from_user.full_name}](tg://user?id={uid})\n"
        f"*Анкета:*\n{form_text}\n\n"
        f"*Класс:* {class_value}\n"
        f"*Выбранная услуга:* {service_text}\n\n"
        f"Если подтверждаете — нажмите кнопку ниже."
    )

    try:
        await bot.send_message(
            ADMIN_ID,
            admin_message,
            parse_mode="Markdown",
            reply_markup=admin_confirm_keyboard(uid, svc)
        )
    except Exception as e:
        logging.exception("Не удалось отправить заявку администратору:")
        # уведомляем пользователя, что произошла ошибка
        await callback.message.answer("К сожалению, произошла ошибка при отправке заявки. Попробуйте позже.")
    finally:
        await callback.answer()  # чтобы убрать "крутилку" у кнопки

# --- Обработчик подтверждения админом (callback_data начинается с confirm_) ---
@dp.callback_query(lambda c: c.data and c.data.startswith("confirm_"))
async def admin_confirm_callback(callback: types.CallbackQuery):
    # формат: confirm_{user_id}_{service_code}
    parts = callback.data.split("_", 2)
    if len(parts) < 3:
        await callback.answer("Неверные данные подтверждения.", show_alert=True)
        return

    _, user_id_str, service_code = parts
    try:
        user_id = int(user_id_str)
    except ValueError:
        await callback.answer("Неверный ID пользователя.", show_alert=True)
        return

    # Отправляем пользователю сообщение с контактом преподавателя
    try:
        await bot.send_message(
            user_id,
            "Преподаватель подтвердил твою заявку! ??\n\n"
            "Свяжись с ним по ссылке:",
            reply_markup=send_contact_keyboard()
        )
    except Exception as e:
        logging.exception("Не удалось отправить сообщение ученику при подтверждении.")
        await callback.answer("Не удалось отправить уведомление ученику (возможно, блокировка).", show_alert=True)
        return

    # Подтверждаем админу
    await callback.message.answer("Ученику отправлен контакт ??")
    await callback.answer("Подтверждение отправлено ученику.")

# --- Запуск поллинга ---
async def main():
    logging.info("Запуск бота...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):

        logging.info("Бот остановлен.")
