"""MongoDB connection + collection accessors."""
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import get_settings

settings = get_settings()
_client = AsyncIOMotorClient(settings.mongo_url)
db = _client[settings.db_name]


def users_col():
    return db.users


def companies_col():
    return db.companies


def documents_col():
    return db.documents


def chat_sessions_col():
    return db.chat_sessions


def chat_messages_col():
    return db.chat_messages


def web_sources_col():
    return db.web_sources


def invites_col():
    return db.invites


def allowlist_col():
    return db.allowlist


def password_resets_col():
    return db.password_resets


async def init_indexes():
    await users_col().create_index("email", unique=True)
    await documents_col().create_index([("created_at", -1)])
    await chat_sessions_col().create_index([("user_id", 1), ("updated_at", -1)])
    await chat_messages_col().create_index([("session_id", 1), ("created_at", 1)])
    await web_sources_col().create_index("url", unique=True)
    await invites_col().create_index("code", unique=True)
    await invites_col().create_index([("company_id", 1), ("is_active", 1)])
    await allowlist_col().create_index([("email", 1), ("company_id", 1)], unique=True)
    # Password reset: TTL index auto-purges expired/consumed token rows, and a
    # unique index on the hashed token prevents the same secret from being
    # accepted twice even if the consumed flag is set out-of-band.
    await password_resets_col().create_index("expires_at", expireAfterSeconds=0)
    await password_resets_col().create_index("token_hash", unique=True)
    await password_resets_col().create_index([("email", 1), ("created_at", -1)])
