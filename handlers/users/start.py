import os
import time
import logging
import re
from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher.filters.builtin import CommandStart, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

from data.config import GOOGLE_CREDENTIALS_FILE, SPREADSHEET_ID, SHEET_NAME, DRIVE_FOLDER_ID
from loader import dp, bot
from states.Tok_Uchun import RequestForm
from datetime import datetime
import pytz

# Asia/Tashkent vaqt zonasi
tz = pytz.timezone('Asia/Tashkent')

# Список администраторов
ADMINS = [973358587]

# Настройки логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Подключение к Google Sheets
def connect_to_google_sheets():
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
        return sheet
    except Exception as e:
        logging.error(f"Ошибка подключения к Google Sheets: {str(e)}")
        raise

# Подключение к Google Drive
def connect_to_google_drive():
    try:
        scope = ['https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
        drive_service = build('drive', 'v3', credentials=creds)
        return drive_service
    except Exception as e:
        logging.error(f"Ошибка подключения к Google Drive: {str(e)}")
        raise

# Создание новой папки
def create_drive_folder(drive_service, folder_name):
    try:
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        folder = drive_service.files().create(body=file_metadata, fields='id').execute()
        folder_id = folder.get('id')
        drive_service.permissions().create(
            fileId=folder_id,
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()
        logging.info(f"Создана новая папка: {folder_name} (ID: {folder_id})")
        return folder_id
    except HttpError as e:
        logging.error(f"Ошибка создания папки: {str(e)}")
        return None

# Проверка существования папки
def check_folder_exists(drive_service, folder_id):
    try:
        folder = drive_service.files().get(fileId=folder_id).execute()
        logging.info(f"Папка существует: {folder['name']} (ID: {folder_id})")
        return True
    except HttpError as e:
        logging.error(f"Папка с ID {folder_id} не найдена: {str(e)}")
        return False

# Загрузка файла в Google Drive
def upload_to_drive(file_path):
    try:
        drive_service = connect_to_google_drive()
        folder_id = DRIVE_FOLDER_ID
        if not check_folder_exists(drive_service, folder_id):
            logging.warning(f"Папка не найдена: {folder_id}. Создаётся новая папка...")
            folder_id = create_drive_folder(drive_service, "Bot Photos Новая")
            if not folder_id:
                logging.error("Не удалось создать новую папку.")
                return None
            logging.info(f"Новый ID папки: {folder_id}")

        file_metadata = {
            'name': os.path.basename(file_path),
            'parents': [folder_id]
        }
        media = MediaFileUpload(file_path, mimetype='image/jpeg')
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        file_id = file.get('id')
        drive_service.permissions().create(
            fileId=file_id,
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()
        logging.info(f"Файл успешно загружен, ID: {file_id}")
        return f"https://drive.google.com/file/d/{file_id}/view"
    except HttpError as e:
        logging.error(f"Ошибка загрузки в Google Drive: {str(e)}")
        return None
    except Exception as e:
        logging.error(f"Общая ошибка: {str(e)}")
        return None

# Клавиатура для местоположения
def get_location_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.add(KeyboardButton("📍 Отправить местоположение", request_location=True))
    return keyboard

# Inline-кнопки для кадастрового номера (есть/нет)
def get_cadastr_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("✅ Кадастр есть!", callback_data="cadastr_yes"))
    keyboard.add(InlineKeyboardButton("❌ Кадастр нет", callback_data="cadastr_no"))
    return keyboard

# Inline-кнопка для начала запроса
def get_request_button():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("📝 Запрос отправить", callback_data="start_request"))
    return keyboard

# Inline-кнопка для перезапуска
def get_restart_button():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🔄 Начать заново", callback_data="restart_request"))
    return keyboard

# Команда /start
@dp.message_handler(CommandStart())
async def bot_start(message: types.Message):
    await message.answer(
        f"<b>Здравствуйте, {message.from_user.full_name}!</b> 🎉\n\n"
        f"Я помогу вам отправить запрос. Нажмите на кнопку ниже, чтобы начать:\n\n"
        f"<i>В любой момент вы можете отменить процесс, введя команду /cancel.</i>",
        parse_mode="HTML",
        reply_markup=get_request_button()
    )
    logging.info(f"Новый пользователь: {message.from_user.id} - {message.from_user.full_name}")

# Обработка inline-кнопки для начала запроса
@dp.callback_query_handler(lambda c: c.data == "start_request")
async def start_request_callback(callback: types.CallbackQuery):
    await RequestForm.contact_name.set()
    await callback.message.answer(
        "<b>Введите контактное лицо</b> (например, имя):",
        parse_mode="HTML"
    )
    await callback.message.delete()  # Удаляем сообщение с кнопкой
    logging.info(f"Пользователь {callback.from_user.id} начал запрос")

# Обработка inline-кнопки для перезапуска
@dp.callback_query_handler(lambda c: c.data == "restart_request", state="*")
async def restart_request_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.finish()  # Текущее состояние сбрасывается
    await RequestForm.contact_name.set()
    await callback.message.answer(
        "<b>Введите контактное лицо</b> (например, имя):",
        parse_mode="HTML"
    )
    await callback.message.delete()  # Удаляем сообщение с кнопкой
    logging.info(f"Пользователь {callback.from_user.id} перезапустил запрос")

# Команда /cancel - полная отмена процесса
@dp.message_handler(Command('cancel'), state='*')
async def cancel_process(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer(
        "<b>Процесс отменён.</b> ✅\nНажмите на кнопку ниже, чтобы начать заново:",
        parse_mode="HTML",
        reply_markup=get_restart_button()
    )
    logging.info(f"Пользователь {message.from_user.id} отменил процесс")

# Контактное лицо
@dp.message_handler(state=RequestForm.contact_name)
async def process_contact_name(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['contact_name'] = message.text
    await RequestForm.next()
    await message.reply(
        "<b>Введите контактный телефон</b> (например, +998901234567 или 901234567):",
        parse_mode="HTML"
    )
    logging.info(f"Пользователь {message.from_user.id} ввел контактное лицо: {message.text}")

# Телефон (ручной ввод)
@dp.message_handler(state=RequestForm.phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone = message.text
    # Проверка формата телефона: либо +998901234567 (12 символов), либо 901234567 (9 символов)
    if not (re.match(r'^\+998[0-9]{9}$', phone) or re.match(r'^[0-9]{9}$', phone)):
        await message.reply(
            "<b>Пожалуйста, введите телефон в правильном формате</b> (например, +998901234567 или 901234567):",
            parse_mode="HTML"
        )
        logging.warning(f"Пользователь {message.from_user.id} ввел неверный формат телефона: {phone}")
        return

    async with state.proxy() as data:
        data['phone'] = phone
    await RequestForm.next()
    await message.reply(
        "<b>Введите адрес</b> (например, Самарканд):",
        parse_mode="HTML"
    )
    logging.info(f"Пользователь {message.from_user.id} ввел телефон: {phone}")

# Адрес
@dp.message_handler(state=RequestForm.address)
async def process_address(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['address'] = message.text
    await RequestForm.next()
    await message.reply(
        "<b>У вас есть кадастровый номер?</b>",
        parse_mode="HTML",
        reply_markup=get_cadastr_keyboard()
    )
    logging.info(f"Пользователь {message.from_user.id} ввел адрес: {message.text}")

# Обработка inline-кнопок для кадастрового номера
@dp.callback_query_handler(lambda c: c.data in ["cadastr_yes", "cadastr_no"], state=RequestForm.cadastr_number)
async def process_cadastr_choice(callback: types.CallbackQuery, state: FSMContext):
    async with state.proxy() as data:
        if callback.data == "cadastr_yes":
            data['has_cadastr'] = "Есть"  # Google Sheets’da "Есть" саqlanadi
        else:
            data['has_cadastr'] = "Нет"  # Google Sheets’da "Нет" саqlanadi

    await RequestForm.transformer_info.set()
    await callback.message.answer(
        "<b>Введите данные о трансформаторе:</b>",
        parse_mode="HTML"
    )
    await callback.message.delete()
    logging.info(f"Пользователь {callback.from_user.id} выбрал: {data['has_cadastr']}")

# Данные трансформатора
@dp.message_handler(state=RequestForm.transformer_info)
async def process_transformer_info(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['transformer_info'] = message.text
    await RequestForm.next()
    await message.reply(
        "<b>Отправьте местоположение</b>",
        parse_mode="HTML",
        reply_markup=get_location_keyboard()
    )
    logging.info(f"Пользователь {message.from_user.id} ввел данные о трансформаторе: {message.text}")

# Местоположение
@dp.message_handler(content_types=['location'], state=RequestForm.location)
async def process_location(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        latitude = message.location.latitude
        longitude = message.location.longitude
        data['location_link'] = f"https://maps.google.com/?q={latitude},{longitude}"
    await RequestForm.next()
    await message.reply(
        "<b>Отправьте фото места:</b>",
        parse_mode="HTML",
        reply_markup=types.ReplyKeyboardRemove()
    )
    logging.info(f"Пользователь {message.from_user.id} отправил местоположение: {data['location_link']}")

@dp.message_handler(state=RequestForm.location)
async def invalid_location(message: types.Message):
    await message.reply(
        "<b>Пожалуйста, отправьте местоположение через кнопку:</b>",
        parse_mode="HTML",
        reply_markup=get_location_keyboard()
    )
    logging.warning(f"Пользователь {message.from_user.id} отправил неверный формат местоположения")

# Фото
@dp.message_handler(content_types=['photo'], state=RequestForm.photo)
async def process_photo(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        # Сохранение фото временно
        photo = message.photo[-1]
        file_info = await bot.get_file(photo.file_id)
        file_path = file_info.file_path
        temp_file = f"temp_{message.from_user.id}_{int(time.time())}.jpg"
        await bot.download_file(file_path, temp_file)

        # Загрузка в Google Drive
        photo_link = upload_to_drive(temp_file)
        if photo_link:
            data['photo_link'] = photo_link
        else:
            data['photo_link'] = ""
            logging.warning(f"Фото для пользователя {message.from_user.id} не загружено")

        # Удаление временного файла
        if os.path.exists(temp_file):
            os.remove(temp_file)

        # Форматирование текущего времени
        current_time = datetime.now(tz)

        # Запись данных в Google Sheets
        try:
            sheet = connect_to_google_sheets()
            sheet.append_row([
                current_time,
                data['contact_name'],
                data['phone'],
                data['address'],
                data['has_cadastr'],  # "Есть" или "Нет"
                data['transformer_info'],
                data['photo_link'],
                data['location_link']
            ])
            logging.info(f"Данные записаны в Google Sheets: {message.from_user.id}")
        except Exception as e:
            logging.error(f"Ошибка записи в Google Sheets: {str(e)}")
            await message.reply(
                "⚠ <b>Произошла ошибка при сохранении данных.</b> Пожалуйста, попробуйте снова.",
                parse_mode="HTML",
                reply_markup=get_restart_button()
            )
            await state.finish()
            return

        # Отправка администратору
        admin_message = (
            f"<b>Новый запрос:</b>\n"
            f"⏰ Время: {current_time}\n"
            f"👤 Контактное лицо: {data['contact_name']}\n"
            f"📞 Телефон: {data['phone']}\n"
            f"🏠 Адрес: {data['address']}\n"
            f"📜 Кадастровый: {data['has_cadastr']}\n"
            f"⚡ Данные трансформатора: {data['transformer_info']}\n"
            f"📍 Местоположение: {data['location_link'] or 'Не указано'}\n"
            f"📸 Фото: {data['photo_link'] or 'Не загружено'}"
        )
        for admin_id in ADMINS:
            try:
                await bot.send_message(int(admin_id), admin_message, parse_mode="HTML")
                if data['photo_link']:
                    await bot.send_message(int(admin_id), data['photo_link'])
                logging.info(f"Запрос отправлен админу: {admin_id}, пользователь: {message.from_user.id}")
            except Exception as e:
                logging.error(f"Ошибка отправки админу {admin_id}: {str(e)}")

        logging.info(f"Пользователь {message.from_user.id} завершил запрос, ссылка на фото: {data['photo_link']}")

    await message.reply(
        "<b>Данные успешно сохранены!</b> ✅\nНажмите на кнопку ниже, чтобы начать заново:",
        parse_mode="HTML",
        reply_markup=get_restart_button()
    )
    await state.finish()

# Неверный формат фото
@dp.message_handler(state=RequestForm.photo)
async def invalid_photo(message: types.Message):
    await message.reply(
        "<b>Пожалуйста, отправьте только фото:</b>",
        parse_mode="HTML"
    )

    logging.warning(f"Пользователь {message.from_user.id} отправил неверный формат фото")
