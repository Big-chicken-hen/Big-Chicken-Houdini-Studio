import os

if os.environ.get("BCS_AUTOSTART") == "1":
    try:
        from studio.runtime_server import start
        start()
    except Exception as exc:
        print("[Big-Chicken Studio] Runtime unavailable:", exc)
