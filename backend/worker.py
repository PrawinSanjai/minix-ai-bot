"""Run a horizontally scalable Redis Streams chat worker process."""

import asyncio
import logging

from services.worker import run_worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


if __name__ == "__main__":
    asyncio.run(run_worker())
