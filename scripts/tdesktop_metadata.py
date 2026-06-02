from pathlib import Path

from opentele.td import shared as td
from opentele.td.configs import QByteArray
from PyQt5.QtCore import QBuffer, QDataStream, QIODevice, QStandardPaths


LskDraft = 0x01
LskDraftPosition = 0x02
LskLegacyImages = 0x03
LskLocations = 0x04
LskLegacyStickerImages = 0x05
LskLegacyAudios = 0x06
LskRecentStickersOld = 0x07
LskBackgroundOldOld = 0x08
LskUserSettings = 0x09
LskRecentHashtagsAndBots = 0x0A
LskStickersOld = 0x0B
LskSavedPeersOld = 0x0C
LskReportSpamStatusesOld = 0x0D
LskSavedGifsOld = 0x0E
LskSavedGifs = 0x0F
LskStickersKeys = 0x10
LskTrustedPeers = 0x11
LskFavedStickers = 0x12
LskExportSettings = 0x13
LskBackgroundOld = 0x14
LskSelfSerialized = 0x15
LskMasksKeys = 0x16
LskCustomEmojiKeys = 0x17
LskSearchSuggestions = 0x18
LskWebviewTokens = 0x19
LskRoundPlaceholder = 0x1A
LskInlineBotsDownloads = 0x1B
LskMediaLastPlaybackPositions = 0x1C
LskBotStorages = 0x1D
LskPrefs = 0x1E

DBI_CACHE_SETTINGS = 0x5C
DBI_SESSION_SETTINGS = 0x4D
FILE_DIALOG_TMP = "tmp"


def extract_telegram_desktop_metadata(tdata: Path, passcode: str | None) -> dict:
    try:
        settings = read_download_settings(tdata, passcode)
    except Exception as error:
        settings = {
            "error": str(error),
            "download_path": None,
            "ask_download_path": None,
        }

    return {
        "download_directory": effective_download_directory(settings),
        "settings": settings,
    }


def read_download_settings(tdata: Path, passcode: str | None) -> dict:
    local_key, account_index = read_local_key_and_account_index(tdata, passcode)
    base_path = account_base_path(tdata, account_index)
    settings_key = read_settings_key(base_path, local_key)
    if not settings_key:
        return {
            "download_path": None,
            "ask_download_path": None,
            "error": "settings key not found",
        }

    settings_file = td.Storage.ReadEncryptedFile(
        td.Storage.ToFilePart(settings_key),
        base_path,
        local_key,
    )

    while not settings_file.stream.atEnd():
        block_id = settings_file.stream.readUInt32()
        if block_id == DBI_CACHE_SETTINGS:
            settings_file.stream.readInt64()
            settings_file.stream.readInt32()
            settings_file.stream.readInt64()
            settings_file.stream.readInt32()
        elif block_id == DBI_SESSION_SETTINGS:
            serialized = QByteArray()
            settings_file.stream >> serialized
            return parse_core_settings(serialized)
        else:
            raise RuntimeError(f"unknown settings block: {block_id}")

    return {
        "download_path": None,
        "ask_download_path": None,
        "error": "session settings block not found",
    }


def read_local_key_and_account_index(tdata: Path, passcode: str | None) -> tuple[td.AuthKey, int]:
    key_data = td.Storage.ReadFile("key_data", str(tdata))
    salt, key_encrypted, info_encrypted = QByteArray(), QByteArray(), QByteArray()
    key_data.stream >> salt >> key_encrypted >> info_encrypted

    passcode_key = td.Storage.CreateLocalKey(
        salt,
        QByteArray((passcode or "").encode("utf-8")),
    )
    key_inner_data = td.Storage.DecryptLocal(key_encrypted, passcode_key)
    local_key = td.AuthKey(key_inner_data.stream.readRawData(256))

    info = td.Storage.DecryptLocal(info_encrypted, local_key)
    count = info.stream.readInt32()
    if count <= 0:
        raise RuntimeError("no Telegram Desktop accounts found")
    account_index = info.stream.readInt32()
    return local_key, account_index


def account_base_path(tdata: Path, account_index: int) -> str:
    data_name = td.Storage.ComposeDataString("data", account_index)
    data_name_key = td.Storage.ComputeDataNameKey(data_name)
    return td.Storage.PathJoin(str(tdata), td.Storage.ToFilePart(data_name_key))


def read_settings_key(base_path: str, local_key: td.AuthKey) -> int:
    map_data = td.Storage.ReadFile("map", base_path)
    legacy_salt, legacy_key_encrypted, map_encrypted = QByteArray(), QByteArray(), QByteArray()
    map_data.stream >> legacy_salt >> legacy_key_encrypted >> map_encrypted
    decrypted = td.Storage.DecryptLocal(map_encrypted, local_key)

    while not decrypted.stream.atEnd():
        key_type = decrypted.stream.readUInt32()
        if key_type in (LskDraft, LskDraftPosition, LskBotStorages):
            skip_key_peer_map(decrypted.stream)
        elif key_type == LskSelfSerialized:
            skip_byte_array(decrypted.stream)
        elif key_type in (LskLegacyImages, LskLegacyStickerImages, LskLegacyAudios):
            skip_legacy_file_map(decrypted.stream)
        elif key_type in (
            LskPrefs,
            LskLocations,
            LskReportSpamStatusesOld,
            LskTrustedPeers,
            LskRecentStickersOld,
            LskBackgroundOldOld,
            LskRecentHashtagsAndBots,
            LskStickersOld,
            LskFavedStickers,
            LskSavedGifsOld,
            LskSavedGifs,
            LskSavedPeersOld,
            LskExportSettings,
            LskSearchSuggestions,
            LskRoundPlaceholder,
            LskInlineBotsDownloads,
            LskMediaLastPlaybackPositions,
        ):
            decrypted.stream.readUInt64()
        elif key_type == LskUserSettings:
            return decrypted.stream.readUInt64()
        elif key_type == LskBackgroundOld:
            decrypted.stream.readUInt64()
            decrypted.stream.readUInt64()
        elif key_type == LskStickersKeys:
            for _ in range(4):
                decrypted.stream.readUInt64()
        elif key_type in (LskMasksKeys, LskCustomEmojiKeys):
            for _ in range(3):
                decrypted.stream.readUInt64()
        elif key_type == LskWebviewTokens:
            skip_byte_array(decrypted.stream)
            skip_byte_array(decrypted.stream)
        else:
            raise RuntimeError(f"unknown map key type: {key_type}")

    return 0


def skip_key_peer_map(stream) -> None:
    count = stream.readUInt32()
    for _ in range(count):
        stream.readUInt64()
        stream.readUInt64()


def skip_legacy_file_map(stream) -> None:
    count = stream.readUInt32()
    for _ in range(count):
        stream.readUInt64()
        stream.readUInt64()
        stream.readUInt64()
        stream.readInt32()


def skip_byte_array(stream) -> None:
    value = QByteArray()
    stream >> value


def parse_core_settings(serialized: QByteArray) -> dict:
    buffer = QBuffer()
    buffer.setBuffer(serialized)
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    stream = QDataStream()
    stream.setDevice(buffer)
    stream.setVersion(QDataStream.Version.Qt_5_1)

    themes_accent_colors = QByteArray()
    stream >> themes_accent_colors
    if stream.atEnd():
        return {
            "download_path": None,
            "ask_download_path": None,
            "error": "core settings did not include download path",
        }

    stream.readInt32()
    stream.readInt32()
    stream.readInt32()
    stream.readInt32()
    ask_download_path = stream.readInt32()
    download_path = stream.readQString()
    download_path_bookmark = QByteArray()
    stream >> download_path_bookmark

    return {
        "download_path": normalize_download_path(download_path),
        "ask_download_path": bool(ask_download_path),
        "error": None,
    }


def normalize_download_path(path: str | None) -> str | None:
    if not path:
        return None
    if path == FILE_DIALOG_TMP:
        return path
    return path if path.endswith("/") else f"{path}/"


def effective_download_directory(settings: dict) -> dict:
    path = settings.get("download_path")
    if path == FILE_DIALOG_TMP:
        return {
            "path": None,
            "source": "tdesktop_temp_download_path",
            "available": False,
        }
    if path:
        return {
            "path": path,
            "source": "tdesktop_configured_download_path",
            "available": True,
        }
    return {
        "path": default_download_path(),
        "source": "tdesktop_default_download_path",
        "available": True,
    }


def default_download_path() -> str:
    downloads = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation)
    return f"{downloads}/Telegram Desktop/"
