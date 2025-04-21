from environs import Env

env = Env()
env.read_env()


BOT_TOKEN = env.str("BOT_TOKEN")
ADMINS = env.list("ADMINS")
IP = env.str("IP")

GOOGLE_CREDENTIALS_FILE = 'tokbot-457507-6dd979a6599a.json'
SPREADSHEET_ID = '1Uh5Xcgq_FdWofXWqwXRJTgXcp9i66SLFmIenfWYHRh4'
SHEET_NAME = 'telegram_bot'
DRIVE_FOLDER_ID = '1Pbv-4U-8ROfUWjNtZ_wSmXf8PBp4LC1M'