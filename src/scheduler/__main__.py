"""Allow ``python -m src.scheduler`` invocation."""

import asyncio

from src.scheduler.main import main

asyncio.run(main())
