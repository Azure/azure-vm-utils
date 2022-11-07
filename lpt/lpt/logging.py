import logging
import sys

logger = logging.getLogger("lpt")


def configure_logging(log_level: int):
    logging.basicConfig(level=log_level)
    logger.setLevel(log_level)
    formatter = logging.Formatter(
        fmt="%(asctime)s.%(msecs)03d|%(levelname)s|%(name)s:%(module)s:%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(log_level)
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Cleanup logging
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("paramiko").setLevel(logging.WARNING)
    logging.getLogger("paramiko").propagate = False
    logging.getLogger("urllib3").handlers = []
    logging.getLogger("urllib3").addHandler(handler)
    logging.getLogger("urllib3").propagate = False
