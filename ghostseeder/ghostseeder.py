"""This Python script spoofs seeding of torrent files to private trackers
by sending fake announces. 

Private trackers often reward bonus points for seeding large torrents 
with few seeders. But trackers don't have an explicit way to verify you 
actually have the files
"""
import argparse
import asyncio
import enum
import logging
import os
import random
import string

from typing import Optional
from urllib.parse import urlencode

import aiolimiter
import flatbencode
import httpx
import semver
import torf

DEBUG = False
# Allow for 10 concurrent announces within a 5 second window. Useful
# especially during a cold start with a lot of torrents:
RATE_LIMIT = aiolimiter.AsyncLimiter(10, 5)
# Default time in between announces unless tracker provides an
# interval (3600 seconds = 1 hour):
DEFAULT_SLEEP_INTERVAL = 3600


logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(message)s",
    level=logging.DEBUG if DEBUG else logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)


def generate_peer_id(client: str, version: semver.VersionInfo) -> str:
    """Generates a unique string that identifies your torrent client to the
    tracker. Uses the "Azureus-style" convention. For more information
    see https://wiki.theory.org/BitTorrentSpecification#peer_id
    """
    # The major, minor, patch numbers are supposed to be represented as hexadecimal
    # and go up to version x.y.15 using 10->A, 11->B, ...16->F
    # See: https://github.com/qbittorrent/qBittorrent/wiki/Frequently-Asked-Questions#What_is_qBittorrent_Peer_ID
    # But this is complicated to deal with so artificially prevent any 2-digit numbers:
    assert (
        len(client) == 2
        and version.major < 10
        and version.minor < 10
        and version.patch < 10
    )

    random_hash = "".join(
        random.choices(string.ascii_uppercase + string.ascii_lowercase, k=12)
    )
    peer_id = f"-{client}{version.major}{version.minor}{version.patch}0-{random_hash}"
    assert len(peer_id) == 20

    logging.info(f"Generating torrent client peer id: {peer_id}")
    return peer_id


def generate_useragent(client: str, version: semver.VersionInfo) -> str:
    # Also see: https://wiki.theory.org/BitTorrentSpecification#peer_id
    # Only qBittorrent is supported rightnow
    client_map = {
        "qB": "qBittorrent",
    }
    client = client_map[client]
    return f"{client}/{version.major}.{version.minor}.{version.patch}"


# See: https://wiki.theory.org/BitTorrentSpecification#Tracker_Request_Parameters
class TrackerRequestEvent(enum.Enum):
    STARTED = "started"
    STOPPED = "stopped"
    COMPLETED = "completed"


class TorrentSpoofer:
    def __init__(self, filepath: str, peer_id: str, useragent: str):
        self.filepath = filepath
        self.torrent = torf.Torrent.read(filepath)
        self.peer_id = peer_id
        self.useragent = useragent
        self.announce_url = self.torrent.metainfo["announce"]

    async def announce(
        self,
        client: httpx.AsyncClient,
        port: int,
        uploaded: int = 0,
        downloaded: int = 0,
        left: int = 0,
        compact: int = 1,
        event: Optional[TrackerRequestEvent] = None,
    ) -> bytes:

        headers = {"User-Agent": self.useragent}
        params = {
            "info_hash": bytes.fromhex(self.torrent.infohash),
            "peer_id": self.peer_id,
            "uploaded": uploaded,
            "downloaded": downloaded,
            "left": left,
            "compact": compact,
            "port": port,
        }
        if event is not None:
            assert isinstance(event, TrackerRequestEvent)
            params["event"] = event.value

        # I'm manually urlencoding the query parameters because httpx doesn't
        # seem to encode the infohash bytestring correctly...
        url = f"{self.announce_url}?{urlencode(params)}"
        logging.info(f"Announcing {self.torrent.name} to {url}")
        response = await client.get(url, headers=headers)
        logging.debug(
            f"For {self.torrent.name} announcement, server returned response:\n\n {response.content}"
        )
        return response.content

    async def announce_forever(self, client: httpx.AsyncClient, port: int):
        num_announces = 1

        while True:
            event = TrackerRequestEvent.STARTED if num_announces == 1 else None

            try:
                contents = await self.announce(client, port, event=event)
            except httpx.HTTPError as exc:
                logging.warning(
                    f"Unable to complete request for {self.torrent.name} exception occurred: {exc}"
                )
                sleep = DEFAULT_SLEEP_INTERVAL
            else:
                # Re-announce again at the given time provided by tracker
                sleep = parse_interval(contents, self.torrent.name)
                num_announces += 1
            logging.info(
                f"Re-announcing (#{num_announces}) {self.torrent.name} in {sleep} seconds..."
            )
            await asyncio.sleep(sleep)

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

                    logging.info(f"Found {filepath}")
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


async def ghostseed(filepath: str, port: int, version: str) -> None:
    version_info = semver.VersionInfo.parse(version)
    peer_id = generate_peer_id("qB", version_info)
    useragent = generate_useragent("qB", version_info)

    torrents = TorrentSpoofer.load_torrents(filepath, peer_id, useragent)
    logging.info("Finished reading in torrent files")
    logging.info(
        f"Tracker announces will use the following settings: (port={port}, peer_id='{peer_id}', user-agent='{useragent}')"
    )

    async with RATE_LIMIT:
        async with httpx.AsyncClient() as client:
            announces = []
            for torrent in torrents:
                announces.append(torrent.announce_forever(client, port))
            await asyncio.gather(*announces)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Enter path to a directory of torrent files"
    )
    parser.add_argument("-f", "--folder", type=str, required=True)
    parser.add_argument("-p", "--port", nargs="?", type=int, const=1, default=6881)
    parser.add_argument("-v", "--version", type=str, default="4.4.5")
    args = parser.parse_args()

    asyncio.run(ghostseed(args.folder, args.port, args.version))
