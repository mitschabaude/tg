#!/usr/bin/env python3
import argparse
import asyncio
import json
from pathlib import Path

from opentele.api import CreateNewSession
from opentele.td import TDesktop
from opentele.td.account import StorageAccount

from tdesktop_metadata import extract_telegram_desktop_metadata


def use_auth_only_tdata_load() -> None:
    def start_auth_only(self: StorageAccount, local_key):
        self._StorageAccount__localKey = local_key
        self.readMtpData()
        try:
            return self.readMtpConfig()
        except Exception:
            return self.config

    StorageAccount.start = start_auth_only


async def import_session(
    tdata: Path,
    session: Path,
    passcode: str | None,
    password: str | None,
) -> dict:
    session.parent.mkdir(parents=True, exist_ok=True)
    telegram_desktop = extract_telegram_desktop_metadata(tdata, passcode)

    use_auth_only_tdata_load()
    desktop = TDesktop(str(tdata), passcode=passcode)
    client = await desktop.ToTelethon(
        session=str(session),
        flag=CreateNewSession,
        password=password,
        receive_updates=False,
    )

    await client.connect()
    try:
        me = await client.get_me()
        return {
            "id": me.id,
            "username": me.username,
            "first_name": me.first_name,
            "last_name": me.last_name,
            "phone_present": bool(getattr(me, "phone", None)),
            "session": str(session) + ".session",
            "telegram_desktop": telegram_desktop,
        }
    finally:
        await client.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tdata", required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--passcode")
    parser.add_argument("--password")
    args = parser.parse_args()

    result = asyncio.run(import_session(
        Path(args.tdata),
        Path(args.session),
        args.passcode,
        args.password,
    ))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
