import argparse
import asyncio

from ghostseeder import ghostseed


def cli():
    parser = argparse.ArgumentParser(
        description="Enter path to a directory of torrent files"
    )
    parser.add_argument("-f", "--folder", type=str, required=True)
    parser.add_argument("-p", "--port", nargs="?", type=int, const=1, default=6881)
    parser.add_argument("-v", "--version", type=str, default="4.4.5")
    args = parser.parse_args()

    asyncio.run(ghostseed(args.folder, args.port, args.version))


if __name__ == "__main__":
    cli()
