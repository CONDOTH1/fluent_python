#!/usr/bin/env python3

"""
Example written following Fluent Python, 2nd Edition
"""

import asyncio
import functools
import sys
from asyncio.trsock import TransportSocket
from typing import cast

from charindex import InvertedIndex, format_result

CRLF = b"\r\n"
PROMPT = b"?>"


async def finder(
    index: InvertedIndex, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    # Get the remote client address to which the socket is connected.
    client = writer.get_extra_info("peername")
    # Handle dialog until control character is received.
    while True:
        # The write method is not a coroutine, just a func
        writer.write(PROMPT)  # Not awaitable
        # Flushes the writer buffer; it's a coroutine, so be driven by await
        await writer.drain()
        # readline is a coroutine that returns bytes
        data = await reader.readline()
        # If no bytes were received, the client closed the connection, so exit
        if not data:
            break
        try:
            # Decode bytes to str, using the UTF-8 encoder (default)
            query = data.decode().strip()
        # Possible Ctrl+C and Telnet sending bytes; if happens this simplifies
        # if by sending null characters
        except UnicodeDecodeError:
            query = "\x00"
        print(f" From {client}: {query!r}")
        if query:
            # Exit the loop if a control or null char was received
            if ord(query[:1]) < 32:
                break
            # Do the search
            results = await search(query, index, writer)
            print(f" From {client}: {results} results.")

    writer.close()
    await writer.wait_closed()
    print(f"Close {client}.")


async def search(query: str, index: InvertedIndex, writer: asyncio.StreamWriter) -> int:
    # Query inverted index
    chars = index.search(query)
    # This generator expression will yield byte strings encoded with UTF-8
    # with the unicode codepoint, the actual char, its name, and a CRLF seq i.e
    # b'U+0039\t9\tDIGIT NINE\r\n'
    lines = (line.encode() + CRLF for line in format_result(chars))
    # Not a coroutine
    writer.writelines(lines)
    # Same as drain on the above
    await writer.drain()
    status_line = f'{"-" * 66} {len(chars)} found'
    writer.write(status_line.encode() + CRLF)
    await writer.drain()
    return len(chars)


async def supervisor(index: InvertedIndex, host: str, port: int):
    # The await quickly gets an instance of asyncio.Server, a TCP socket server.
    # By default, start_server creates and starts the server, so it's ready to 
    # receive connections.
    server = await asyncio.start_server(
        # Callback to call when client connection starts. Can be func or coro
        # but needs exactly two args: asyncio.StreamReader/StreamWriter.
        functools.partial(finder, index),
        host,
        port
    )
    # Cast is for typeshed
    socket_list = cast(tuple[TransportSocket, ...], server.sockets)
    addr = socket_list[0].getsockname()
    print(f"Serving on {addr}. Hit CTRL-C to stop.")
    await server.serve_forever()


def main(host: str = "127.0.0.1", port_arg: str = "2323"):
    port = int(port_arg)
    print("Building index.")
    index: InvertedIndex = InvertedIndex()
    try:
        # Start the event loop
        asyncio.run(supervisor(index=index, host=host, port=port))
    except KeyboardInterrupt:
        print("\nServer shut down.")


if __name__ == "__main__":
    main(*sys.argv[1:])
