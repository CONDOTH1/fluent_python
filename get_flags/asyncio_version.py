"""
Example written following Fluent Python, 2nd Edition
"""

import asyncio
from collections import Counter
from http import HTTPStatus
from pathlib import Path

import httpx
import tqdm

from common import main, DownloadStatus, save_flag

DEFAULT_CONCUR_REQ = 5
MAX_CONCUR_REQ = 1000


async def get_flag(client: httpx.AsyncClient, base_url: str, cc: str) -> bytes:
    """
    Make HTTP request to provided url for specified flag
    """
    url = f"{base_url}/{cc}/{cc}.gif".lower()
    resp = await client.get(url, timeout=3.1, follow_redirects=True)
    resp.raise_for_status()
    return resp.content


async def get_country(client: httpx.AsyncClient, base_url: str, cc: str) -> str:
    """
    This coroutine returns a string with the country name (all going well)
    """
    url = f"{base_url}/{cc}/metadata.json".lower()
    resp = await client.get(url, timeout=3.1, follow_redirects=True)
    resp.raise_for_status()
    metadata = resp.json()
    return metadata["country"]


async def download_one(
    client: httpx.AsyncClient,
    cc: str,
    base_url: str,
    semaphore: asyncio.Semaphore,
    verbose: bool,
) -> DownloadStatus:
    """
    Asynchronous function with semaphore (primitive to limit the number of
    simultaneous operations) to get flag and handle errors properly
    """
    try:
        # Setting up a context with a semaphore so the program as a whole
        # doesn't block; only this coroutine is suspended when the semaphore
        # counter is zero.
        async with semaphore:
            image = await get_flag(client, base_url, cc)
        # good practice to hold semaphores and locks for the shortest possible
        # time
        async with semaphore:
            country = await get_country(client, base_url, cc)
    except httpx.HTTPStatusError as exc:
        res = exc.response
        if res.status_code == HTTPStatus.NOT_FOUND:
            status = DownloadStatus.NOT_FOUND
            msg = f"not found: {res.url}"
        else:
            raise
    else:
        # Format country name for filename format
        filename = country.replace(" ", "_")
        # Saving the image is an I/O operation. To avoid blocking the event
        # loop run save_flag in a thread.
        await asyncio.to_thread(save_flag, image, f"{filename}.gif")
        status = DownloadStatus.OK
        msg = "OK"
    if verbose and msg:
        print(cc, msg)
    return status


async def supervisor(
    cc_list: list[str], base_url: str, verbose: bool, concur_req: int
) -> Counter[DownloadStatus]:
    """
    Orchestrate the asynchronous fetching of multiple flags concurrently
    using the get download_one function and error handling

    This function takes the same args as 'download_many', but it cannot be
    invoked directly from main because it's a coroutine  and not a plain
    function.
    """
    counter: Counter[DownloadStatus] = Counter()
    # create a Semophore that will not allow more than concur_req active
    # coroutines among those using this semaphore. The value of concur_req
    # is computed by the main function from common.py, based on command-line
    # options and constants set in each example.
    semaphore = asyncio.Semaphore(concur_req)
    async with httpx.AsyncClient() as client:
        # create a list of coroutine objects, one per call to the
        # 'download_one' coroutine.
        to_do = [
            download_one(client, cc, base_url, semaphore, verbose)
            for cc in sorted(cc_list)
        ]
        # get an iterator that will return coroutine objects as they are done.
        to_do_iter = asyncio.as_completed(to_do)
        if not verbose:
            # wrap the as_complete iterator with the tqdm generator function to
            # display progress.
            to_do_iter = tqdm.tqdm(to_do_iter, total=len(cc_list))
        error: httpx.HTTPError | None = None
        for coro in to_do_iter:
            try:
                status = await coro
            except httpx.HTTPStatusError as exc:
                error_msg = "HTTP error {resp.status_code} - {resp.reason_phrase}"
                error_msg = error_msg.format(res=exc.response)
                # necessary assignment as exc is scoped to except only
                error = exc
            except KeyboardInterrupt:
                break

            if error:
                status = DownloadStatus.ERROR
                if verbose:
                    # extract url from request
                    url = str(error.request.url)
                    # extract the name fo the file to display the cc next.
                    cc = Path(url).stem.upper()
                    print(f"{cc} error: {error_msg}")
            counter[status] += 1

    return counter


def download_many(
    cc_list: list[str],
    base_url: str,
    verbose: bool,
    concur_req: int,
) -> Counter[DownloadStatus]:
    coro = supervisor(cc_list, base_url, verbose, concur_req)
    # instantiate the supervisor coroutine object and pass it to the event loop
    # with asyncio.run, collecting the counter supervisor returns when the
    # event loop ends.
    counts = asyncio.run(coro)

    return counts


if __name__ == "__main__":
    main(download_many, DEFAULT_CONCUR_REQ, MAX_CONCUR_REQ)
