"""Run a worker that claims pending chat jobs from PostgreSQL."""

import asyncio
import logging

from services.worker import run_worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


if __name__ == "__main__":
    asyncio.run(run_worker())
