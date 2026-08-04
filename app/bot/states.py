from aiogram.fsm.state import State, StatesGroup


class RegistrationState(StatesGroup):
    waiting_contact = State()
    waiting_confirmation = State()


class SupportState(StatesGroup):
    waiting_message = State()
