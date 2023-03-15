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
        help="A folder containing torrent files",
    )
    parser.add_argument(
        "-p",
        "--port",
        nargs="?",
        type=int,
        const=1,
        default=6881,
        help="Port number to announce to the tracker",
    )
    parser.add_argument(
        "-v",
        "--version",
        type=str,
        default="4.4.5",
        help="Specific torrent client version number to spoof",
    )
    parser.add_argument(
        "-r",
        "--max-requests",
        type=int,
        help="Maximum number of HTTP announces per second. Useful especially at startup to mitigate sending a large burst of announces at once.",
    )
    parser.add_argument(
        "-s",
        "--seed",
        type=int,
        help="Optional random seed to use to make peer id generation deterministic",
    )
    args = parser.parse_args()

    asyncio.run(
        ghostseed(args.folder, args.port, args.version, args.max_requests, args.seed)
    )


if __name__ == "__main__":
    cli()
