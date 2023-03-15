# Ghostseeder 
![GitHub CI](https://github.com/jephdo/ghostseeder/actions/workflows/test.yml/badge.svg)

This Python script spoofs seeding of torrent files to private trackers
by sending fake announces. 

Private trackers usually reward bonus points for seeding a lot of torrents. But 
at the same time, trackers don't have an explicit way to verify you actually have the files

## Setup 

Tested with Python v3.9+
```
$ git clone https://github.com/jephdo/ghostseeder.git
$ python -m pip intall .
$ python -m ghostseeder --help
usage: __main__.py [-h] -f FOLDER [-p [PORT]] [-v VERSION]

Enter path to a directory of torrent files

optional arguments:
  -h, --help            show this help message and exit
  -f FOLDER, --folder FOLDER
                        A directory containing `.torrent` files. Torrent files should be from a private tracker and the announce url should contain your unique passkey
  -p [PORT], --port [PORT]
                        The port number announced to the tracker to receive incoming connections. Used if you want to change the port number announced to the tracker. Optional, defaults to `6881`
  -v VERSION, --version VERSION
                        The version of qBittorrent that you want to announce to the tracker. This info is used to generate the peer id and user agent string. Setting `-v '3.3.16'` will use qBittorrent
                        v3.3.16. Optional, defaults to `'4.3.9'`
  -r MAX_REQUESTS, --max-requests MAX_REQUESTS
                        Maximum number of allowed HTTP announces per second. Useful especially at startup to mitigate sending a large burst of announces at once.
  -s SEED, --seed SEED  Optional random seed used to make peer-id generation deterministic
```
  
Script will announce itself as a [qBittorrent](https://github.com/qbittorrent/qBittorrent) client

## Example Usage
Add torrent files to a folder:
```
$ tree torrents/
torrents/
├── archlinux-2022.11.01-x86_64.iso.torrent
├── freebsd
│      ├── FreeBSD-11.4-RELEASE-amd64-disc1.iso.torrent
│      ├── FreeBSD-12.2-RELEASE-amd64-disc1.iso.torrent
│      └── FreeBSD-13.1-RELEASE-amd64-disc1.iso.torrent
└── ubuntu-22.10-desktop-amd64.iso.torrent

1 directory, 5 files
$ python cli.py -f torrents/
```

The script will search for all `.torrent` files in the folder passed to it. For example, run this on your server/seedbox:

```
$ nohup python -m ghostseeder -f torrents/ &>> output.log &
```

This will run the script in the background and store logs in `output.log`

**Example output**
```
$ python -m ghostseeder -f torrents/ -p 59097
2023-03-10 21:48:30 INFO     Generating torrent client peer id: -qB4450-OcPetHlvbFeW
2023-03-10 21:48:30 INFO     Searching for torrent files located under 'torrents/'
2023-03-10 21:48:30 INFO     Found 5 torrent files
2023-03-10 21:48:30 INFO     Reading and parsing torrent files...
2023-03-10 21:48:30 INFO     Finished reading in torrent files
2023-03-10 21:48:30 INFO     Tracker announces will use the following settings: (port=59097, peer_id='-qB4450-OcPetHlvbFeW', user-agent='qBittorrent/4.4.5')
2023-03-10 21:48:31 INFO     Announcing ubuntu-22.10-desktop-amd64.iso 
2023-03-10 21:48:31 INFO     Re-announcing (#1) ubuntu-22.10-desktop-amd64.iso in 1800 seconds...
...
```

## Details of this script

Every private torrent has an announce url to the tracker containing a unique passkey (e.g. `https://flacsfor.me/123456789abcdefg37ss9t0awe3dlyqs/announce`). When a torrent client begins seeding a torrent, it uses this url to send parameters describing the current state of the torrent (including how much has been downloaded and uploaded). All information about the torrent is self-reported by the client.

Key request parameters to modify are `info_hash` and `left`. `info_hash` identifies the specific torrent and `left` states how many bytes needed to finish downloading the torrent. This script repeatedly sends HTTP requests to the tracker, setting `left=0`, declaring to the tracker that you are actively seeding the torrent:
```
GET https://flacsfor.me/123456789abcdefg37ss9t0awe3dlyqs/announce?info_hash=%D5E%DB%06v%15D%8CLx%21%3B%C5v%1DNf%8E%1B4&peer_id=-qB4450-OcPetHlvbFeW&uploaded=0&downloaded=0&left=0&compact=1&port=6881
```

More details on the HTTP protocol between trackers and peers [here](https://wiki.theory.org/BitTorrentSpecification#Tracker_HTTP.2FHTTPS_Protocol) 
