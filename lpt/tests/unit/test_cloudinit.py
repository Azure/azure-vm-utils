import datetime

from lpt import cloudinit


def test_start_event():
    log_line = "2022-10-07 11:47:53,209 - handlers.py[DEBUG]: start: azure-ds/_get_data: _get_data"

    entry = cloudinit.CloudInitEntry.parse(log_line)

    assert entry == cloudinit.CloudInitEntry(
        log_line=log_line,
        log_level="DEBUG",
        message="_get_data",
        python_module="handlers.py",
        result=None,
        timestamp_realtime=datetime.datetime(2022, 10, 7, 11, 47, 53, 209000),
        timestamp_monotonic=0.0,
        event_type="start",
        module="azure-ds/_get_data",
        stage=None,
    )


def test_finish_event():
    log_line = "2022-10-07 11:51:25,375 - handlers.py[DEBUG]: finish: azure-ds/_get_data: SUCCESS: _get_data"

    entry = cloudinit.CloudInitEntry.parse(log_line)

    assert entry == cloudinit.CloudInitEntry(
        log_line=log_line,
        log_level="DEBUG",
        message="_get_data",
        python_module="handlers.py",
        result="SUCCESS",
        timestamp_realtime=datetime.datetime(2022, 10, 7, 11, 51, 25, 375000),
        timestamp_monotonic=0.0,
        event_type="finish",
        module="azure-ds/_get_data",
        stage=None,
    )


def test_log():
    log_line = "2022-10-03 20:36:23,366 - main.py[DEBUG]: Closing stdin."

    entry = cloudinit.CloudInitEntry.parse(log_line)

    assert entry == cloudinit.CloudInitEntry(
        log_line=log_line,
        log_level="DEBUG",
        message="Closing stdin.",
        python_module="main.py",
        result=None,
        timestamp_realtime=datetime.datetime(2022, 10, 3, 20, 36, 23, 366000),
        timestamp_monotonic=0.0,
        event_type="log",
        module=None,
        stage=None,
    )


def test_reference_point():
    log_line = "2022-10-03 20:36:23,366 - util.py[DEBUG]: Cloud-init v. 22.2-0ubuntu1~20.04.3 running 'init-local' at Mon, 03 Oct 2022 20:36:23 +0000. Up 20497.78 seconds."

    entry = cloudinit.CloudInitEntry.parse(log_line)

    assert entry == cloudinit.CloudInitEntry(
        log_line=log_line,
        log_level="DEBUG",
        message="Cloud-init v. 22.2-0ubuntu1~20.04.3 running 'init-local' at Mon, 03 Oct 2022 20:36:23 +0000. Up 20497.78 seconds.",
        python_module="util.py",
        result=None,
        timestamp_realtime=datetime.datetime(2022, 10, 3, 20, 36, 23, 366000),
        timestamp_monotonic=20497.78,
        event_type="log",
        module=None,
        stage=None,
    )


def test_log_with_colons():
    log_line = "2022-10-07 14:10:48,482 - __init__.py[DEBUG]: {'MIME-Version': '1.0', 'Content-Type': 'text/x-not-multipart', 'Content-Disposition': 'attachment; filename=\"part-001\"'}"

    entry = cloudinit.CloudInitEntry.parse(log_line)

    assert entry == cloudinit.CloudInitEntry(
        log_line=log_line,
        log_level="DEBUG",
        message="{'MIME-Version': '1.0', 'Content-Type': 'text/x-not-multipart', 'Content-Disposition': 'attachment; filename=\"part-001\"'}",
        python_module="__init__.py",
        result=None,
        timestamp_realtime=datetime.datetime(2022, 10, 7, 14, 10, 48, 482000),
        timestamp_monotonic=0.0,
        event_type="log",
        module=None,
        stage=None,
    )


def test_finish_not_greedy():
    log_line = "2022-10-07 14:05:51,827 - handlers.py[DEBUG]: finish: init-network/check-cache: SUCCESS: restored from cache with run check: DataSourceAzure [seed=/dev/sr0]"

    entry = cloudinit.CloudInitEntry.parse(log_line)

    assert entry == cloudinit.CloudInitEntry(
        log_line=log_line,
        log_level="DEBUG",
        message="restored from cache with run check: DataSourceAzure [seed=/dev/sr0]",
        python_module="handlers.py",
        result="SUCCESS",
        timestamp_realtime=datetime.datetime(2022, 10, 7, 14, 5, 51, 827000),
        timestamp_monotonic=0.0,
        event_type="finish",
        module="check-cache",
        stage="init-network",
    )
