import uvicorn
import log

log.setup()

if __name__ == "__main__":
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, log_config=log.UVICORN_LOG_CONFIG)
