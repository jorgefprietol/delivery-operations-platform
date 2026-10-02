import logging

import uvicorn

logging.basicConfig(level=logging.INFO, format="%(message)s")
uvicorn.run("delivery.api:create_app", factory=True, host="0.0.0.0", port=8080, access_log=False)
