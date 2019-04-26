from .base import MIDDLEWARE

MIDDLEWARE.append('simple_history.middleware.HistoryRequestMiddleware')

SIMPLE_HISTORY_HISTORY_ID_USE_UUID = True

SIMPLE_HISTORY_EDIT = False
