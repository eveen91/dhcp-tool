"""Do not expose raw request URLs, exception messages or tracebacks in server logs."""

from gunicorn.glogging import Logger

from config.logging import SafeFormatter


class SafeGunicornLogger(Logger):
    def setup(self, cfg):
        super().setup(cfg)
        for handler in self.error_log.handlers:
            handler.setFormatter(SafeFormatter())
