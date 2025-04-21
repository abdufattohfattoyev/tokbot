from aiogram.dispatcher.filters.state import StatesGroup,State


class RequestForm(StatesGroup):
    contact_name = State()
    phone = State()
    address = State()
    cadastr_number = State()
    transformer_info = State()
    location = State()
    photo = State()