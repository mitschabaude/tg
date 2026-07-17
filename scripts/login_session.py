#!/usr/bin/env python3
"""Interactive login that creates a fresh agent session without Telegram Desktop tdata.

Unlike bootstrap_tdesktop_session.py, this does not read any local Telegram
storage. It performs a normal MTProto login (QR or phone code) that an existing
Telegram client (e.g. Telegram for macOS) approves. This is the path to use when
Telegram Desktop is not installed.
"""
import argparse
import asyncio
import sys
from pathlib import Path

import qrcode
from opentele.api import API
from opentele.tl import TelegramClient
from telethon.errors import SessionPasswordNeededError


def session_base(path: str) -> str:
    return path[:-8] if path.endswith(".session") else path


def prompt(text: str) -> str:
    # Prompts must go to stderr so stdout stays clean for the caller.
    print(text, end="", file=sys.stderr, flush=True)
    return input().strip()


def render_qr(url: str) -> None:
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(out=sys.stderr, invert=True)
    print(f"\nOr open this link on a logged-in device: {url}\n", file=sys.stderr)


async def qr_login(client: TelegramClient) -> None:
    print(
        "Scan this QR with Telegram on your phone or Mac:\n"
        "  Settings -> Devices -> Link Desktop Device\n",
        file=sys.stderr,
    )
    qr = await client.qr_login()
    render_qr(qr.url)
    while True:
        try:
            await qr.wait(timeout=30)
            return
        except asyncio.TimeoutError:
            await qr.recreate()
            print("QR expired, refreshing...\n", file=sys.stderr)
            render_qr(qr.url)
        except SessionPasswordNeededError:
            password = prompt("Two-step verification password: ")
            await client.sign_in(password=password)
            return


async def phone_login(client: TelegramClient) -> None:
    phone = prompt("Phone number (international format, e.g. +15551234567): ")
    await client.send_code_request(phone)
    code = prompt("Login code (sent to your logged-in Telegram app): ")
    try:
        await client.sign_in(phone=phone, code=code)
    except SessionPasswordNeededError:
        password = prompt("Two-step verification password: ")
        await client.sign_in(password=password)


async def run(session: str, method: str) -> None:
    base = session_base(session)
    Path(base).parent.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(base, api=API.TelegramDesktop, receive_updates=False)
    await client.connect()
    try:
        if await client.is_user_authorized():
            me = await client.get_me()
            print(f"already authorized as user_id={me.id}", file=sys.stderr)
        else:
            if method == "qr":
                await qr_login(client)
            else:
                await phone_login(client)
        me = await client.get_me()
        name = " ".join(filter(None, [me.first_name, me.last_name])) or "(unnamed)"
        handle = f" @{me.username}" if me.username else ""
        print(f"logged in as {name}{handle} user_id={me.id}", file=sys.stderr)
        print(f"session: {base}.session", file=sys.stderr)
    finally:
        await client.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", required=True)
    parser.add_argument("--method", choices=["qr", "phone"], default="qr")
    args = parser.parse_args()
    asyncio.run(run(args.session, args.method))


if __name__ == "__main__":
    main()
