import asyncio
import hashlib
import random

from urllib.parse import urlparse, parse_qs, urlencode

import flatbencode
import httpx
import pytest
import semver

from pytest_httpx import HTTPXMock

from ghostseeder.ghostseeder import (
    DEFAULT_SLEEP_INTERVAL,
    generate_peer_id,
    generate_useragent,
    parse_interval,
    TorrentClient,
    TorrentSpoofer,
    TrackerRequestEvent,
)


def test_parse_interval(successful_tracker_response):
    bytestring = flatbencode.encode(successful_tracker_response)

    assert (
        parse_interval(bytestring, "dummy") == successful_tracker_response[b"interval"]
    )


def test_parse_interval_uses_default_interval_on_failure():
    bad_tracker_response = b"you sent me garbage - no info hash"
    assert parse_interval(bad_tracker_response, "dummy") == DEFAULT_SLEEP_INTERVAL


@pytest.mark.parametrize(
    "client,version,user_agent",
    [
        (TorrentClient.qBittorrent, "4.4.5", "qBittorrent/4.4.5"),
        (TorrentClient.qBittorrent, "4.3.9", "qBittorrent/4.3.9"),
        (TorrentClient.qBittorrent, "3.3.16", "qBittorrent/3.3.16"),
        (TorrentClient.qBittorrent, "3.2.1", "qBittorrent/3.2.1"),
    ],
)
def test_user_agent_string_generation(
    client: TorrentClient, version: str, user_agent: str
):
    version_info = semver.VersionInfo.parse(version)
    assert generate_useragent(client, version_info) == user_agent


@pytest.mark.parametrize(
    "client,version,peer_id",
    [
        (TorrentClient.qBittorrent, "4.4.5", "-qB4450-McTfgDArNMzY"),
        (TorrentClient.qBittorrent, "4.3.9", "-qB4390-McTfgDArNMzY"),
        (TorrentClient.qBittorrent, "3.2.1", "-qB3210-McTfgDArNMzY"),
    ],
)
def test_peer_id_generation(client: TorrentClient, version: str, peer_id: str):
    random.seed(3)
    version_info = semver.VersionInfo.parse(version)
    assert generate_peer_id(client, version_info) == peer_id


@pytest.mark.parametrize(
    "client,version",
    [
        (TorrentClient.qBittorrent, "10.3.9"),
        (TorrentClient.qBittorrent, "4.16.5"),
        (TorrentClient.qBittorrent, "3.3.14"),
    ],
)
def test_peer_id_generation_fails_on_large_version_numbers(
    client: TorrentClient, version: str
):
    version_info = semver.VersionInfo.parse(version)
    with pytest.raises(ValueError):
        generate_peer_id(client, version_info)


class TestLoadingTorrents:
    def generate_directory_tree(self, tmp_path, filelist, metainfo):
        files = [tmp_path / filename for filename in filelist]
        for filepath in files:
            folder = filepath.parent
            folder.mkdir(parents=True, exist_ok=True)
            with open(filepath, "wb") as f:
                f.write(flatbencode.encode(metainfo))
        return files

    def test_torrent_file_parses_correctly(self, tmp_path, valid_metainfo):
        filename = "[abc]test.torrent"
        filepath = tmp_path / filename
        with open(filepath, "wb") as f:
            f.write(flatbencode.encode(valid_metainfo))

        spoof = TorrentSpoofer(
            filepath, peer_id="-qB4450-McTfgDArNMzY", useragent="qBittorrent/4.4.5"
        )

        assert spoof.announce_url == valid_metainfo[b"announce"].decode()
        assert (
            spoof.infohash
            == hashlib.sha1(flatbencode.encode(valid_metainfo[b"info"])).hexdigest()
        )
        assert spoof.name == valid_metainfo[b"info"][b"name"].decode()

    def test_load_subdirectories(self, tmp_path, valid_metainfo):
        files = [
            "a/apple.torrent",
            "a/b/banana.torrent",
            "a/b/c/d/e/orange.torrent",
            "pineapple.torrent",
        ]

        files = self.generate_directory_tree(tmp_path, files, valid_metainfo)
        torrents = TorrentSpoofer.load_torrents(
            tmp_path, peer_id="-qB4450-McTfgDArNMzY", useragent="qBittorrent/4.4.5"
        )
        assert len(files) == len(torrents)

        files = set(f.as_posix() for f in files)
        for torrent in torrents:
            assert torrent.filepath in files

    def test_load_subdirectories_skips_non_torrents(self, tmp_path, valid_metainfo):
        files = [
            "a/apple.torrent",
            "a/banana.jpg",
            "a/b/c/orange.mp3",
            "pineapple.torrent",
        ]
        files = self.generate_directory_tree(tmp_path, files, valid_metainfo)
        torrents = TorrentSpoofer.load_torrents(
            tmp_path, peer_id="-qB4450-McTfgDArNMzY", useragent="qBittorrent/4.4.5"
        )
        files = set(f.as_posix() for f in files if f.suffix == ".torrent")
        assert len(torrents) == len(files)
        for torrent in torrents:
            assert torrent.filepath in files


@pytest.mark.asyncio
async def test_url_and_query_params_constructed_correctly(
    httpx_mock: HTTPXMock, valid_torrent: TorrentSpoofer
):
    httpx_mock.add_response()

    params = {
        "port": 6881,
        "uploaded": 500,
        "downloaded": 200,
        "left": 5,
        "compact": False,
        "event": TrackerRequestEvent.COMPLETED,
    }
    async with httpx.AsyncClient() as client:
        response = await valid_torrent.announce(client, **params)

    assert response.status_code == 200

    url = response.url
    assert valid_torrent.announce_url == f"{url.scheme}://{url.host}"

    parsed_url = urlparse(str(url))
    parsed_params = parse_qs(parsed_url.query)

    assert params["port"] == int(parsed_params["port"][0])
    assert params["uploaded"] == int(parsed_params["uploaded"][0])
    assert params["downloaded"] == int(parsed_params["downloaded"][0])
    assert params["left"] == int(parsed_params["left"][0])
    assert params["compact"] == bool(int(parsed_params["compact"][0]))
    assert params["event"] == TrackerRequestEvent(parsed_params["event"][0])

    assert valid_torrent.peer_id == parsed_params["peer_id"][0]


@pytest.mark.asyncio
async def test_user_agent_string_in_header(
    httpx_mock: HTTPXMock, valid_torrent: TorrentSpoofer
):
    httpx_mock.add_response()
    async with httpx.AsyncClient() as client:
        response = await valid_torrent.announce(client, port=6881)

    assert valid_torrent.useragent == response.request.headers["User-Agent"]


@pytest.mark.asyncio
async def test_announce_counting(httpx_mock: HTTPXMock, valid_torrent: TorrentSpoofer):
    httpx_mock.add_response()
    async with httpx.AsyncClient() as client:
        for i in range(10):
            await valid_torrent.announce(client, port=6881)
            assert i + 1 == valid_torrent.num_announces


@pytest.mark.asyncio
async def test_infohash_url_encoded_correctly(
    httpx_mock: HTTPXMock, valid_torrent: TorrentSpoofer
):
    encoded_infohash = urlencode({"info_hash": bytes.fromhex(valid_torrent.infohash)})
    httpx_mock.add_response()
    async with httpx.AsyncClient() as client:
        response = await valid_torrent.announce(client, port=6881)

    assert encoded_infohash in str(response.url)


@pytest.mark.asyncio
async def test_spoofer_sends_final_stop_announce(
    httpx_mock: HTTPXMock, valid_torrent: TorrentSpoofer, caplog
):
    async def run():
        httpx_mock.add_response()
        async with httpx.AsyncClient() as client:
            await valid_torrent.announce_forever(client, port=6881)

    task = asyncio.create_task(run())
    await asyncio.sleep(0.01)
    task.cancel()
    # Have to actually wait a bit for the logging output in the `finally:` clause
    # to even reach logging output:
    await asyncio.sleep(0.01)
    assert "&event=stopped" in caplog.text
