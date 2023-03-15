import argparse
import asyncio

from ghostseeder import ghostseed


def cli():
    parser = argparse.ArgumentParser(
        description="Enter path to a directory of torrent files"
    )
    parser.add_argument(
        "-f",
        "--folder",
        type=str,
        required=True,
        help="A directory containing `.torrent` files. Torrent files should be from a private tracker and the announce url should contain your unique passkey",
    )
    parser.add_argument(
        "-p",
        "--port",
        nargs="?",
        type=int,
        const=1,
        default=6881,
        help="The port number announced to the tracker to receive incoming connections. Used if you want to change the port number announced to the tracker. Optional, defaults to `6881`",
    )
    parser.add_argument(
        "-v",
        "--version",
        type=str,
        default="4.3.9",
        help="The version of qBittorrent that you want to announce to the tracker. This info is used to generate the peer id and user agent string. Setting `-v '3.3.16'` will use qBittorrent v3.3.16. Optional, defaults to  `'4.3.9'`",
    )
    parser.add_argument(
        "-r",
        "--max-requests",
        type=int,
        help="Maximum number of allowed HTTP announces per second. Useful especially at startup to mitigate sending a large burst of announces at once.",
    )
    parser.add_argument(
        "-s",
        "--seed",
        type=int,
        help="Optional random seed used to make peer-id generation deterministic",
    )
    args = parser.parse_args()

    asyncio.run(
        ghostseed(args.folder, args.port, args.version, args.max_requests, args.seed)
    )


if __name__ == "__main__":
    cli()
