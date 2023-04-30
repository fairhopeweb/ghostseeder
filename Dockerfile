# syntax=docker/dockerfile:1

FROM python:3.11-slim-buster

ARG PORT=6881
ENV PORT=$PORT

ARG VERSION="4.3.9"
ENV VERSION=$VERSION

WORKDIR /app

COPY . /app

RUN pip3 install /app

VOLUME /torrents

CMD python3 -m ghostseeder -f /torrents -p $PORT -v $VERSION