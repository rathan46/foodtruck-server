from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import get_settings

client: AsyncIOMotorClient | None = None


async def connect() -> None:
    global client
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongodb_uri, uuidRepresentation="standard")
    await client.admin.command("ping")


async def disconnect() -> None:
    if client:
        client.close()


def db():
    if client is None:
        raise RuntimeError("MongoDB is not connected")
    return client[get_settings().mongodb_db]
