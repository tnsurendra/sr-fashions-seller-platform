
"""Run locally/scheduled: recover pending callbacks and prune delivered replay tombstones."""
import asyncio
from sqlalchemy.orm import Session
from app.database import get_engine
from app.ondc.config import get_ondc_settings
from app.ondc.registry.client import RegistryClient
from app.ondc.clients.http import SignedClient
from app.ondc.protocol.service import DiscoveryService
from app.ondc.protocol.replay import cleanup

async def main():
    settings = get_ondc_settings()
    service = DiscoveryService(settings, RegistryClient(settings), SignedClient(settings))
    with Session(get_engine()) as db:
        await service.resume(db)
        cleanup(db)

if __name__ == "__main__":
    asyncio.run(main())
