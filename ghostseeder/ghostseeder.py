"""This Python script spoofs seeding of torrent files to private trackers
by sending fake announces. 

Private trackers often reward bonus points for seeding large torrents 
with few seeders. But trackers don't have an explicit way to verify you 
actually have the files
"""
import asyncio
import enum
import hashlib
import logging
import os
import random
import string
from typing import Optional
from urllib.parse import urlencode

import flatbencode
import httpx
import semver
from asynciolimiter import StrictLimiter

DEBUG = False
MAX_REQUESTS_PER_SECOND = 1
# Default time in between announces unless tracker provides an
# interval (3600 seconds = 1 hour):
DEFAULT_SLEEP_INTERVAL = 3600


logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(message)s",
    level=logging.DEBUG if DEBUG else logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)
# Also see: https://wiki.theory.org/BitTorrentSpecification#peer_id for
# a list of 2-character codes.
# Only qBittorrent is supported right now since it's a hassle to figure out
# the correct user agent strings for every client
class TorrentClient(enum.Enum):
    qBittorrent = "qB"
    # Deluge = "DE"
    # Transmission = "TR"


def generate_peer_id(
    client: TorrentClient, version: semver.VersionInfo, seed: Optional[int] = None
) -> str:
    """Generates a unique string that identifies your torrent client to the
    tracker. Uses the "Azureus-style" convention. For more information
    see https://wiki.theory.org/BitTorrentSpecification#peer_id
    """
    # The major, minor, patch numbers are supposed to be represented as hexadecimal
    # and go up to version x.y.15 using 10->A, 11->B, ...16->F
    # See: https://github.com/qbittorrent/qBittorrent/wiki/Frequently-Asked-Questions#What_is_qBittorrent_Peer_ID
    # But this is complicated to deal with so artificially prevent any 2-digit numbers:
    if version.major > 9 or version.minor > 9 or version.patch > 9:
        raise ValueError("Version numbers must be single digits only: {}")
    if seed is not None:
        random.seed(seed)
    random_hash = "".join(
        random.choices(string.ascii_uppercase + string.ascii_lowercase, k=12)
    )
    peer_id = (
        f"-{client.value}{version.major}{version.minor}{version.patch}0-{random_hash}"
    )
    logging.info(f"Generating torrent client peer id: {peer_id}")
    return peer_id


def generate_useragent(client: TorrentClient, version: semver.VersionInfo) -> str:
    return f"{client.name}/{version.major}.{version.minor}.{version.patch}"


# See: https://wiki.theory.org/BitTorrentSpecification#Tracker_Request_Parameters
class TrackerRequestEvent(enum.Enum):
    STARTED = "started"
    STOPPED = "stopped"
    COMPLETED = "completed"


class TorrentSpoofer:
    def __init__(self, filepath: str, peer_id: str, useragent: str):
        self.filepath = filepath
        with open(filepath, "rb") as f:
            contents = f.read()
        torrent_info = flatbencode.decode(contents)
        self.peer_id = peer_id
        self.useragent = useragent
        self.announce_url = torrent_info[b"announce"].decode()
        self.name = torrent_info[b"info"][b"name"].decode()
        self.infohash = hashlib.sha1(
            flatbencode.encode(torrent_info[b"info"])
        ).hexdigest()
        self.encoded_infohash = bytes.fromhex(self.infohash)
        self.num_announces = 0

    async def announce(
        self,
        client: httpx.AsyncClient,
        port: int,
        uploaded: int = 0,
        downloaded: int = 0,
        left: int = 0,
        compact: bool = True,
        event: Optional[TrackerRequestEvent] = None,
    ) -> httpx.Response:
        headers = {"User-Agent": self.useragent}
        params = {
            "info_hash": self.encoded_infohash,
            "peer_id": self.peer_id,
            "uploaded": uploaded,
            "downloaded": downloaded,
            "left": left,
            # This is a boolean that is sent as '0' or '1'.
            # See: https://wiki.theory.org/BitTorrentSpecification#Tracker_Request_Parameters
            "compact": int(compact),
            "port": port,
        }
        if event is not None:
            assert isinstance(event, TrackerRequestEvent)
            params["event"] = event.value

        # I'm manually urlencoding the query parameters because httpx doesn't
        # seem to encode the infohash bytestring correctly...
        url = f"{self.announce_url}?{urlencode(params)}"
        logging.info(f"Announcing {self.name}")
        response = await client.get(url, headers=headers)
        logging.debug(
            f"For {self.name} announcement ({url}) server returned response:\n\n {response.content}"
        )
        self.num_announces += 1
        return response

    async def announce_forever(
        self, client: httpx.AsyncClient, limit: StrictLimiter, port: int
    ):
        try:
            while True:
                if self.num_announces == 0:
                    event = TrackerRequestEvent.STARTED
                else:
                    event = None

                await limit.wait()
                try:
                    response = await self.announce(client, port, event=event)
                except httpx.HTTPError as exc:
                    logging.warning(
                        f"Unable to complete request for {self.name} exception occurred: {exc}"
                    )
                    sleep = DEFAULT_SLEEP_INTERVAL
                else:
                    # Re-announce again at the given time provided by tracker
                    sleep = parse_interval(response.content, self.name)
                logging.info(
                    f"Re-announcing (#{self.num_announces}) {self.name} in {sleep} seconds..."
                )
                await asyncio.sleep(sleep)
        finally:
            logging.info(
                f"Received shutdown signal...sending final announce: {self.name}"
            )
            await self.announce(client, port, event=TrackerRequestEvent.STOPPED)

    @classmethod
    def load_torrents(
        cls, folderpath: str, peer_id: str, useragent: str
    ) -> list["TorrentSpoofer"]:
        """Recursively find and parse through all torrent files in a directory

        folderpath: folder containing torrent files
        peer_id: The BitTorrent protocol peer id used for announces
        useragent: The user agent string to be used in HTTP requests when announcing
        """
        logging.info(f"Searching for torrent files located under '{folderpath}'")

        torrents = []
        for root, dirs, files in os.walk(folderpath):
            for file in files:
                if file.endswith(".torrent"):
                    filepath = os.path.join(root, file)

                    logging.debug(f"Found {filepath}")
                    torrents.append(filepath)

        logging.info(f"Found {len(torrents)} torrent files")
        logging.info("Reading and parsing torrent files...")
        return [cls(filepath, peer_id, useragent) for filepath in torrents]


def parse_interval(response_bytes: bytes, torrent_name: str) -> int:
    try:
        data = flatbencode.decode(response_bytes)
    except flatbencode.DecodingError:
        logging.warning(
            f"Unable to parse server response for {torrent_name}:\n{response_bytes}"
        )
        sleep = DEFAULT_SLEEP_INTERVAL
    else:
        sleep = data.get(b"interval", DEFAULT_SLEEP_INTERVAL)
    return sleep


async def ghostseed(
    filepath: str,
    port: int,
    version: str,
    max_requests: Optional[int] = None,
    seed: Optional[int] = None,
) -> None:
    version_info = semver.VersionInfo.parse(version)
    peer_id = generate_peer_id(TorrentClient.qBittorrent, version_info, seed)
    useragent = generate_useragent(TorrentClient.qBittorrent, version_info)

    torrents = TorrentSpoofer.load_torrents(filepath, peer_id, useragent)
    logging.info("Finished reading in torrent files")
    logging.info(
        f"Tracker announces will use the following settings: (port={port}, peer_id='{peer_id}', user-agent='{useragent}')"
    )

    if max_requests is None:
        max_requests = MAX_REQUESTS_PER_SECOND
    limit = StrictLimiter(max_requests)

    async with httpx.AsyncClient() as client:
        announces = []
        for torrent in torrents:
            announces.append(torrent.announce_forever(client, limit, port))
        await asyncio.gather(*announces)
