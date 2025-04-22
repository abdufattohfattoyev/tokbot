from aiogram.dispatcher.filters.state import State, StatesGroup


class RequestForm(StatesGroup):
    manager_name = State()
    contact_name = State()
    phone = State()
    address = State()
    cadastr_number = State()
    has_transformer = State()
    transformer_power = State()
    free_power = State()
    station = State()
    location = State()
    location_info = State()
    photo = State()
