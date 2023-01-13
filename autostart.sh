#!/bin/bash
ps -ef | pgrep -fl ghostseeder.py
# if not found - equals to 1, start it
if [ $? -eq 1 ] 
then
    echo "Ghostseeder not running"
    DIR="$(cd "$(dirname "$0")" && pwd)"

    nohup $DIR/env/bin/python $DIR/ghostseeder/ghostseeder.py -f $DIR/torrents/ -p 55570 &>> $DIR/output.log &
fi