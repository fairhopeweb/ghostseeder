from collections import OrderedDict

import pytest
import flatbencode

from ghostseeder.ghostseeder import TorrentSpoofer


# fmt: off
@pytest.fixture
def valid_singlefile_metainfo():
    return OrderedDict([ 
        (b'announce', b'http://localhost'),
        (b'comment', b'Test comment'),
        (b'created by', b'Author'),
        (b'creation date', 1677139471),
        (b'info', OrderedDict([
            (b'length', 500000),
            (b'name', b'Torrent for testing'),
            (b'piece length', 32768),
            (b'pieces', b'\x00' * 20 * 16),
            (b'private', 1)
        ]))
    ]) # type: ignore

@pytest.fixture
def valid_multifile_metainfo():
    return OrderedDict([ 
        (b'announce', b'http://localhost'),
        (b'comment', b'Test comment'),
        (b'created by', b'Author'),
        (b'creation date', 1677139471),
        (b'info', OrderedDict([
            (b'files', [{b'length': 123, b'path': [b'A file']},
                        {b'length': 456, b'path': [b'Another file']},
                        {b'length': 789, b'path': [b'A', b'third', b'file in a subdir']}]),
            (b'name', b'Torrent for testing'),
            (b'piece length', 32768),
            (b'pieces', b'\x00' * 20),
            (b'private', 1)
        ]))
    ]) # type: ignore


@pytest.fixture
def successful_tracker_response():
    return OrderedDict([
        (b"complete", 1965), 
        (b"incomplete", 29), 
        (b"interval", 1800), 
        (b"peers", b"")
    ])
# fmt: on


@pytest.fixture
def valid_torrent(tmp_path, valid_singlefile_metainfo):
    filename = "test.torrent"
    filepath = tmp_path / filename
    with open(filepath, "wb") as f:
        f.write(flatbencode.encode(valid_singlefile_metainfo))

    return TorrentSpoofer(
        filepath, peer_id="-qB4450-McTfgDArNMzY", useragent="qBittorrent/4.4.5"
    )
