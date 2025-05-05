
import os
import time
import logging
import re
import json
from datetime import datetime

import pytz
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

tz = pytz.timezone('Asia/Tashkent')

# Adminlar ro‘yxati
ADMINS = [973358587]

# Log sozlamalari
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# JSON faylini o‘qish
def load_users():
    try:
        if os.path.exists('users.json'):
            with open('users.json', 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logging.error(f"users.json o‘qishda xato: {str(e)}")
        return {}

# JSON fayliga yozish
def save_users(users):
    try:
        with open('users.json', 'w') as f:
            json.dump(users, f, indent=4)
        logging.info("users.json muvaffaqiyatli yangilandi")
    except Exception as e:
        logging.error(f"users.json yozishda xato: {str(e)}")

# Google Sheets ga ulanish
def connect_to_google_sheets():
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
        return sheet
    except Exception as e:
        logging.error(f"Google Sheets ulanishda xato: {str(e)}")
        raise

# Google Drive ga ulanish
def connect_to_google_drive():
    try:
        scope = ['https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
        drive_service = build('drive', 'v3', credentials=creds)
        return drive_service
    except Exception as e:
        logging.error(f"Google Drive ulanishda xato: {str(e)}")
        raise

# Papka mavjudligini tekshirish
def check_folder_exists(drive_service, folder_id):
    try:
        folder = drive_service.files().get(fileId=folder_id).execute()
        logging.info(f"Papka mavjud: {folder['name']} (ID: {folder_id})")
        return True
    except HttpError as e:
        logging.error(f"Papka ID {folder_id} topilmadi: {str(e)}")
        return False

# Yangi papka yaratish
def create_drive_folder(drive_service, folder_name, parent_folder_id=None):
    try:
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        if parent_folder_id:
            file_metadata['parents'] = [parent_folder_id]
        folder = drive_service.files().create(body=file_metadata, fields='id, webViewLink').execute()
        folder_id = folder.get('id')
        drive_service.permissions().create(
            fileId=folder_id,
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()
        logging.info(f"Yangi papka yaratildi: {folder_name} (ID: {folder_id})")
        return folder_id, folder.get('webViewLink')
    except HttpError as e:
        logging.error(f"Papka yaratishda xato: {str(e)}")
        return None, None

# Google Drive ga fayl yuklash
def upload_to_drive(file_path, mime_type, folder_id):
    try:
        drive_service = connect_to_google_drive()
        file_metadata = {
            'name': os.path.basename(file_path),
            'parents': [folder_id]
        }
        media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True, chunksize=1024*1024)
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        file_id = file.get('id')
        drive_service.permissions().create(
            fileId=file_id,
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()
        logging.info(f"Fayl muvaffaqiyatli yuklandi, ID: {file_id}")
        return file_id
    except HttpError as e:
        logging.error(f"Google Drive ga yuklashda xato: {str(e)}")
        return None
    except Exception as e:
        logging.error(f"Umumiy xato: {str(e)}")
        return None

# Manzil uchun klaviatura
def get_location_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.add(KeyboardButton("📍 Отправить местоположение", request_location=True))
    return keyboard

# Kadastr uchun inline tugmalar
def get_cadastr_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("✅ Кадастр есть", callback_data="cadastr_yes"))
    keyboard.add(InlineKeyboardButton("❌ Кадастр нет", callback_data="cadastr_no"))
    return keyboard

# Transformator uchun inline tugmalar
def get_transformer_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("✅ Трансформатор есть", callback_data="transformer_yes"))
    keyboard.add(InlineKeyboardButton("❌ Трансформатор нет", callback_data="transformer_no"))
    return keyboard

# So‘rov boshlash tugmasi
def get_request_button():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("📝 Начать запрос", callback_data="start_request"))
    return keyboard

# Qayta boshlash tugmasi
def get_restart_button():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🔄 Начать заново", callback_data="restart_request"))
    return keyboard

# Stansiya tanlash uchun inline tugmalar
def get_station_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("20кВт", callback_data="station_20kwt"))
    keyboard.add(InlineKeyboardButton("60кВт", callback_data="station_60kwt"))
    keyboard.add(InlineKeyboardButton("80кВт", callback_data="station_80kwt"))
    keyboard.add(InlineKeyboardButton("120кВт", callback_data="station_120kwt"))
    keyboard.add(InlineKeyboardButton("160кВт", callback_data="station_160kwt"))
    return keyboard

# Yakunlash uchun inline tugma
def get_finish_button():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("✅ Завершить", callback_data="finish_upload"))
    return keyboard


# /start komandasi
@dp.message_handler(CommandStart())
async def bot_start(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    users = load_users()
    if user_id in users:
        await RequestForm.contact_name.set()
        async with state.proxy() as data:
            data['manager_name'] = users[user_id]['manager_name']
        await message.answer(
            f"<b>Здравствуйте, {message.from_user.full_name}!</b> 🎉\n"
            f"Текущий менеджер: {users[user_id]['manager_name']}\n"
            f"Введите контактное лицо:",
            parse_mode="HTML"
        )
    else:
        await RequestForm.manager_name.set()
        await message.answer(
            f"<b>Здравствуйте, {message.from_user.full_name}!</b> 🎉\n\n"
            f"Пожалуйста, введите имя менеджера:\n\n"
            f"<i>В любой момент вы можете отменить процесс, введя команду /cancel.</i>",
            parse_mode="HTML"
        )
    logging.info(f"Yangi foydalanuvchi: {user_id} - {message.from_user.full_name}")

# /change_manager komandasi
@dp.message_handler(Command('change_manager'), state='*')
async def change_manager_command(message: types.Message, state: FSMContext):
    await state.finish()
    await RequestForm.change_manager.set()
    await message.answer(
        "<b>Введите новое имя менеджера:</b>",
        parse_mode="HTML"
    )
    logging.info(f"Foydalanuvchi {message.from_user.id} menejer ismini o‘zgartirishni boshladi")

# Menejer ismini o‘zgartirish
@dp.message_handler(state=RequestForm.change_manager)
async def process_change_manager(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    manager_name = message.text
    users = load_users()
    users[user_id] = {'manager_name': manager_name}
    save_users(users)
    await message.answer(
        f"<b>Имя менеджера успешно изменено на:</b> {manager_name}\n"
        f"Нажмите на кнопку ниже, чтобы начать запрос:",
        parse_mode="HTML",
        reply_markup=get_request_button()
    )
    await state.finish()
    logging.info(f"Foydalanuvchi {user_id} menejer ismini o‘zgartirdi: {manager_name}")

# So‘rov boshlash tugmasi
@dp.callback_query_handler(lambda c: c.data == "start_request")
async def start_request_callback(callback: types.CallbackQuery, state: FSMContext):
    user_id = str(callback.from_user.id)
    users = load_users()
    if user_id in users:
        await RequestForm.contact_name.set()
        async with state.proxy() as data:
            data['manager_name'] = users[user_id]['manager_name']
        await callback.message.answer(
            f"<b>Текущий менеджер:</b> {users[user_id]['manager_name']}\n"
            f"<b>Введите контактное лицо:</b>",
            parse_mode="HTML"
        )
    else:
        await RequestForm.manager_name.set()
        await callback.message.answer(
            "<b>Пожалуйста, введите имя менеджера:</b>",
            parse_mode="HTML"
        )
    await callback.message.delete()
    logging.info(f"Foydalanuvchi {user_id} so‘rovni boshladi")

# Menejer ismi
@dp.message_handler(state=RequestForm.manager_name)
async def process_manager_name(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    manager_name = message.text
    users = load_users()
    users[user_id] = {'manager_name': manager_name}
    save_users(users)
    async with state.proxy() as data:
        data['manager_name'] = manager_name
    await RequestForm.contact_name.set()
    await message.reply(
        "<b>Введите контактное лицо:</b>",
        parse_mode="HTML"
    )
    logging.info(f"Foydalanuvchi {user_id} menejer ismini kiritdi: {manager_name}")

# Qayta boshlash
@dp.callback_query_handler(lambda c: c.data == "restart_request", state="*")
async def restart_request_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.finish()
    user_id = str(callback.from_user.id)
    users = load_users()
    if user_id in users:
        await RequestForm.contact_name.set()
        async with state.proxy() as data:
            data['manager_name'] = users[user_id]['manager_name']
        await callback.message.answer(
            f"<b>Текущий менеджер:</b> {users[user_id]['manager_name']}\n"
            f"<b>Введите контактное лицо:</b>",
            parse_mode="HTML"
        )
    else:
        await RequestForm.manager_name.set()
        await callback.message.answer(
            "<b>Пожалуйста, введите имя менеджера:</b>",
            parse_mode="HTML"
        )
    await callback.message.delete()
    logging.info(f"Foydalanuvchi {user_id} so‘rovni qayta boshladi")

# /cancel komandasi
@dp.message_handler(Command('cancel'), state='*')
async def cancel_process(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer(
        "<b>Процесс отменён.</b> ✅\nНажмите на кнопку ниже, чтобы начать заново:",
        parse_mode="HTML",
        reply_markup=get_request_button()
    )
    logging.info(f"Foydalanuvchi {message.from_user.id} jarayonni bekor qildi")

# Kontakt shaxs
@dp.message_handler(state=RequestForm.contact_name)
async def process_contact_name(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['contact_name'] = message.text
    await RequestForm.phone.set()
    await message.reply(
        "<b>Введите контактный телефон:</b> (например, +998901234567 или 901234567)",
        parse_mode="HTML"
    )
    logging.info(f"Foydalanuvchi {message.from_user.id} kontakt shaxsni kiritdi: {message.text}")

# Telefon
@dp.message_handler(state=RequestForm.phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone = message.text
    if not (re.match(r'^\+998[0-9]{9}$', phone) or re.match(r'^[0-9]{9}$', phone)):
        await message.reply(
            "<b>Пожалуйста, введите телефон в правильном формате:</b> (например, +998901234567 или 901234567)",
            parse_mode="HTML"
        )
        logging.warning(f"Foydalanuvchi {message.from_user.id} noto‘g‘ri telefon formati: {phone}")
        return
    async with state.proxy() as data:
        data['phone'] = phone
    await RequestForm.address.set()
    await message.reply(
        "<b>Введите адрес:</b> (например, Самарканд)",
        parse_mode="HTML"
    )
    logging.info(f"Foydalanuvchi {message.from_user.id} telefon kiritdi: {phone}")

# Manzil
@dp.message_handler(state=RequestForm.address)
async def process_address(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['address'] = message.text
    await RequestForm.cadastr_number.set()
    await message.reply(
        "<b>У вас есть кадастровый номер?</b>",
        parse_mode="HTML",
        reply_markup=get_cadastr_keyboard()
    )
    logging.info(f"Foydalanuvchi {message.from_user.id} manzil kiritdi: {message.text}")

# Kadastr tanlash
@dp.callback_query_handler(lambda c: c.data in ["cadastr_yes", "cadastr_no"], state=RequestForm.cadastr_number)
async def process_cadastr_choice(callback: types.CallbackQuery, state: FSMContext):
    async with state.proxy() as data:
        data['has_cadastr'] = "Есть" if callback.data == "cadastr_yes" else "Нет"
    await RequestForm.has_transformer.set()
    await callback.message.answer(
        "<b>У вас есть трансформатор?</b>",
        parse_mode="HTML",
        reply_markup=get_transformer_keyboard()
    )
    await callback.message.delete()
    logging.info(f"Foydalanuvchi {callback.from_user.id} kadastr tanladi: {data['has_cadastr']}")

# Transformator tanlash
@dp.callback_query_handler(lambda c: c.data in ["transformer_yes", "transformer_no"], state=RequestForm.has_transformer)
async def process_transformer_choice(callback: types.CallbackQuery, state: FSMContext):
    async with state.proxy() as data:
        if callback.data == "transformer_yes":
            data['has_transformer'] = "Есть"
            await RequestForm.transformer_power.set()
            await callback.message.answer(
                "<b>Введите мощность ТП (кВт):</b>",
                parse_mode="HTML"
            )
        else:
            data['has_transformer'] = "Нет"
            data['transformer_power'] = ""
            data['free_power'] = ""
            data['station'] = ""
            await RequestForm.location.set()
            await callback.message.answer(
                "<b>Отправьте местоположение:</b>",
                parse_mode="HTML",
                reply_markup=get_location_keyboard()
            )
    await callback.message.delete()
    logging.info(f"Foydalanuvchi {callback.from_user.id} transformator tanladi: {data['has_transformer']}")

# TP quvvati
@dp.message_handler(state=RequestForm.transformer_power)
async def process_transformer_power(message: types.Message, state: FSMContext):
    power = message.text
    if not re.match(r'^\d+$', power):
        await message.reply("<b>Пожалуйста, введите мощность ТП в виде числа (кВт):</b>", parse_mode="HTML")
        logging.warning(f"Foydalanuvchi {message.from_user.id} noto‘g‘ri TP quvvati formati: {power}")
        return
    async with state.proxy() as data:
        data['transformer_power'] = power
    await RequestForm.free_power.set()
    await message.reply("<b>Введите свободную мощность ТП (кВт):</b>", parse_mode="HTML")
    logging.info(f"Foydalanuvchi {message.from_user.id} TP quvvatini kiritdi: {power}")

# Bo‘sh quvvat
@dp.message_handler(state=RequestForm.free_power)
async def process_free_power(message: types.Message, state: FSMContext):
    free_power = message.text
    if not re.match(r'^\d+$', free_power):
        await message.reply("<b>Пожалуйста, введите свободную мощность ТП в виде числа (кВт):</b>", parse_mode="HTML")
        logging.warning(f"Foydalanuvchi {message.from_user.id} noto‘g‘ri bo‘sh quvvat formati: {free_power}")
        return
    async with state.proxy() as data:
        data['free_power'] = free_power
    await RequestForm.station.set()
    await message.reply("<b>Выберите станцию:</b>", parse_mode="HTML", reply_markup=get_station_keyboard())
    logging.info(f"Foydalanuvchi {message.from_user.id} bo‘sh quvvatni kiritdi: {free_power}")

# Stansiya tanlash
@dp.callback_query_handler(lambda c: c.data.startswith("station_"), state=RequestForm.station)
async def process_station(callback: types.CallbackQuery, state: FSMContext):
    station_mapping = {
        "station_20kwt": "20кВт",
        "station_60kwt": "60кВт",
        "station_80kwt": "80кВт",
        "station_120kwt": "120кВт",
        "station_160kwt": "160кВт"
    }
    station = station_mapping[callback.data]
    async with state.proxy() as data:
        data['station'] = station
    await RequestForm.location.set()
    await callback.message.answer("<b>Отправьте местоположение:</b>", parse_mode="HTML", reply_markup=get_location_keyboard())
    await callback.message.delete()
    logging.info(f"Foydalanuvchi {callback.from_user.id} stansiya tanladi: {station}")

# Manzil
@dp.message_handler(content_types=['location'], state=RequestForm.location)
async def process_location(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        latitude = message.location.latitude
        longitude = message.location.longitude
        data['location_link'] = f"https://maps.google.com/?q={latitude},{longitude}"
    await RequestForm.location_info.set()
    await message.reply(
        "<b>Введите дополнительную информацию о местоположении:</b> (например, ориентиры, описание места)",
        parse_mode="HTML",
        reply_markup=types.ReplyKeyboardRemove()
    )
    logging.info(f"Foydalanuvchi {message.from_user.id} manzil yubordi: {data['location_link']}")

@dp.message_handler(state=RequestForm.location)
async def invalid_location(message: types.Message):
    await message.reply(
        "<b>Пожалуйста, отправьте местоположение через кнопку:</b>",
        parse_mode="HTML",
        reply_markup=get_location_keyboard()
    )
    logging.warning(f"Foydalanuvchi {message.from_user.id} noto‘g‘ri manzil formati")

# Qo‘shimcha manzil ma’lumotlari
@dp.message_handler(state=RequestForm.location_info)
async def process_location_info(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['location_info'] = message.text
        drive_service = connect_to_google_drive()
        folder_name = f"Request_{message.from_user.id}_{datetime.now(tz).strftime('%Y-%m-%d_%H-%M')}"
        folder_id, folder_link = create_drive_folder(drive_service, folder_name, DRIVE_FOLDER_ID)
        if folder_id:
            data['folder_id'] = folder_id
            data['folder_link'] = folder_link
        else:
            data['folder_id'] = DRIVE_FOLDER_ID
            data['folder_link'] = f"https://drive.google.com/drive/folders/{DRIVE_FOLDER_ID}"
    await RequestForm.media_upload.set()
    await message.reply(
        "<b>Отправьте фото или видео места:</b>",
        parse_mode="HTML"
    )
    logging.info(f"Foydalanuvchi {message.from_user.id} qo‘shimcha manzil ma’lumotini kiritdi: {message.text}")

# Media fayllar (rasm yoki video)
@dp.message_handler(content_types=['photo', 'video'], state=RequestForm.media_upload)
async def process_media(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        file_type = 'photo' if message.photo else 'video'
        file_id = message.photo[-1].file_id if message.photo else message.video.file_id
        file_info = await bot.get_file(file_id)
        file_path = file_info.file_path
        file_ext = '.jpg' if message.photo else '.mp4'
        mime_type = 'image/jpeg' if message.photo else 'video/mp4'

        temp_file = f"temp_{message.from_user.id}_{int(time.time())}_{file_type}{file_ext}"

        loading_message = await message.reply("<b>Загружается...</b>", parse_mode="HTML")

        await bot.download_file(file_path, temp_file)

        folder_id = data.get('folder_id', DRIVE_FOLDER_ID)
        file_id = upload_to_drive(temp_file, mime_type, folder_id)
        if file_id:
            await loading_message.edit_text(
                f"<b>{'Фото' if file_type == 'photo' else 'Видео'} успешно загружено!</b> ✅\n"
                f"Отправьте ещё фото/видео или завершите:",
                parse_mode="HTML",
                reply_markup=get_finish_button()
            )
        else:
            await loading_message.edit_text(
                "<b>Ошибка при загрузке файла.</b> ❌\n"
                f"Попробуйте снова или завершите:",
                parse_mode="HTML",
                reply_markup=get_finish_button()
            )
            logging.warning(f"{file_type.capitalize()} fayl yuklanmadi, foydalanuvchi: {message.from_user.id}")

        if os.path.exists(temp_file):
            os.remove(temp_file)

        logging.info(f"Foydalanuvchi {message.from_user.id} {file_type} yukladi, papka ID: {folder_id}")

# Noto‘g‘ri media formati
@dp.message_handler(state=RequestForm.media_upload, content_types=types.ContentType.ANY)
async def invalid_media(message: types.Message):
    await message.reply(
        "<b>Пожалуйста, отправьте только фото или видео:</b>\n"
        f"Или завершите процесс:",
        parse_mode="HTML",
        reply_markup=get_finish_button()
    )
    logging.warning(f"Foydalanuvchi {message.from_user.id} noto‘g‘ri media formati yubordi")

# Yakunlash tugmasi
@dp.callback_query_handler(lambda c: c.data == "finish_upload", state=RequestForm.media_upload)
async def process_finish_upload(callback: types.CallbackQuery, state: FSMContext):
    async with state.proxy() as data:
        current_time = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        try:
            sheet = connect_to_google_sheets()
            folder_link = data.get('folder_link', "Не загружено")
            manager_name = data.get('manager_name', "Не указано")
            sheet.append_row([
                manager_name,
                current_time,
                data['contact_name'],
                data['phone'],
                data['address'],
                data['has_cadastr'],
                data['has_transformer'],
                data['transformer_power'],
                data['free_power'],
                data['station'],
                folder_link,
                data['location_link'],
                data['location_info']
            ])
            logging.info(f"Ma’lumotlar Google Sheets ga yozildi: {callback.from_user.id}")
        except Exception as e:
            logging.error(f"Google Sheets ga yozishda xato: {str(e)}")
            await callback.message.answer(
                "⚠ <b>Произошла ошибка при сохранении данных.</b> Попробуйте снова.",
                parse_mode="HTML",
                reply_markup=get_restart_button()
            )
            await state.finish()
            return

        admin_message = (
            f"<b>Новый запрос:</b>\n"
            f"👤 Имя менеджера: {manager_name}\n"
            f"⏰ Время: {current_time}\n"
            f"👤 Контактное лицо: {data['contact_name']}\n"
            f"📞 Телефон: {data['phone']}\n"
            f"🏠 Адрес: {data['address']}\n"
            f"📜 Кадастровый: {data['has_cadastr']}\n"
            f"⚡ Трансформатор: {data['has_transformer']}\n"
            f"🔌 Мощность ТП: {data['transformer_power'] or 'Не указано'} кВт\n"
            f"🔋 Свободная мощность ТП: {data['free_power'] or 'Не указано'} кВт\n"
            f"🏭 Станция: {data['station'] or 'Не указано'}\n"
            f"📍 Местоположение: {data['location_link'] or 'Не указано'}\n"
            f"ℹ Доп. информация: {data['location_info'] or 'Не указано'}\n"
            f"📸/🎥 Медиа: {folder_link}"
        )
        for admin_id in ADMINS:
            try:
                await bot.send_message(int(admin_id), admin_message, parse_mode="HTML")
                logging.info(f"So‘rov admin ga yuborildi: {admin_id}, foydalanuvchi: {callback.from_user.id}")
            except Exception as e:
                logging.error(f"Admin ga yuborishda xato {admin_id}: {str(e)}")

        logging.info(f"Foydalanuvchi {callback.from_user.id} so‘rovni yakunladi, papka havolasi: {folder_link}")

    await callback.message.answer(
        "<b>Данные успешно сохранены!</b> ✅\nНажмите на кнопку ниже, чтобы начать заново:",
        parse_mode="HTML",
        reply_markup=get_request_button()
    )
    await state.finish()
    await callback.message.delete()
