
"""Run locally/scheduled: recover pending callbacks and prune delivered replay tombstones."""
import asyncio
import argparse
from sqlalchemy.orm import Session
from app.database import get_engine
from app.ondc.config import get_ondc_settings
from app.ondc.registry.client import RegistryClient
from app.ondc.clients.http import SignedClient
from app.ondc.protocol.service import DiscoveryService
from app.ondc.protocol.replay import cleanup
from app.ondc.catalog.scheduler import schedule_due, dispatch_due

async def run_once():
    settings = get_ondc_settings()
    service = DiscoveryService(settings, RegistryClient(settings), SignedClient(settings))
    with Session(get_engine()) as db:
        await service.resume(db)
        schedule_due(db)
        await dispatch_due(db, settings, service.client)
        cleanup(db)

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true")
    args = parser.parse_args()
    while True:
        try:
            await run_once()
        except Exception:
            if not args.loop:
                raise
        if not args.loop:
            return
        await asyncio.sleep(15)

if __name__ == "__main__":
    asyncio.run(main())
