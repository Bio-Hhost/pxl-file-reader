from pathlib import Path
from typing import Iterator
from io import BufferedReader # for type checking
import numpy as np
import logging

# See https://www.dash0.com/guides/logging-in-python
logger = logging.getLogger(__name__)

# Helper function for debugging
def print_hex(array):
    [print(f'{i:02x}', end=' ') for i in array]
    print()

class pxl_frame:
    def __init__(self, fh: BufferedReader, width: int, height: int) -> None:
        self.offset = fh.tell()
        logger.warning('Warning: This toolkit is experimental. Interpret results with care.')
        logger.debug(f'Parsing frame at offset 0x{self.offset:x}:')

        # First five bytes contain timestamp. Read into five_bytes buffer so
        # that we can check for EOF
        five_bytes = fh.read(5)
        if not five_bytes:
            logger.debug('  EOF reached.')
            raise StopIteration # EOF
        self.timestamp = int.from_bytes(five_bytes, 'little')
        logger.debug(f'  timestamp: {self.timestamp}')

        self.tag = int.from_bytes(fh.read(2), 'little') # FIXME: Figure out what this is
        logger.debug(f'  tag:        {self.tag}')

        compressed_size = int.from_bytes(fh.read(4), 'little')
        logger.debug(f'  block size: {compressed_size}')

        self.compressed_frame = fh.read(compressed_size)

        self.width = width
        self.height = height

    @property
    def pixel_array(self) -> np.ndarray:
        # Each row with nonzero photon events is encoded as follows:
        # - Header: 11 bits with row number, 11 bits with non-zero pixel count
        # - Payload: pairs of 11 bits with col number, 12 bits with pixel value

        data = self.compressed_frame
        # Pepare image (we will return this)
        image = np.zeros((self.height, self.width), dtype=np.int16)
        bit_pos = 0
        total_bits = len(data) * 8

        # We need the ability to read n bits where n is not a multiple of 8.
        # FIXME: Use class with clean implementation for bit-reading?
        def read_bits(n):
            nonlocal bit_pos
            ret = 0
            for i in range(n):
                byte_idx = (bit_pos + i) // 8
                bit_idx = (bit_pos + i) % 8
                ret |= ((data[byte_idx] >> bit_idx) & 1) << i
            bit_pos += n
            return ret

        while bit_pos + 22 <= total_bits:
            row = read_bits(11)
            count = read_bits(11)

            for i in range(count):
                if bit_pos + 23 > total_bits:
                    logger.error(f'Ran out of bits while decoding pixel {i} in row {row}')
                    break

                col = read_bits(11)
                val = read_bits(12)
                if row >= self.height or col >= self.width or count == 0:
                    logger.error(f'Error while unpacking frame: row={row}, col={col}, count={count}')
                    break
                image[row, col] = val
        return image


class pxl_file(Iterator[pxl_frame]):

    def __init__(self, file: Path) -> None:
        logger.info(f'Opening PXL file "{file}"')
        self.fh = open(file, 'rb')
        
        # Process header
        header = self.fh.read(0x45d) # Payload starts at 0x45d
        if header[:4] != b'PXL ':
            raise RuntimeError('Not a PXL container (missing PXL magic).')

        # TODO: Parse more header content?
        self.n_frames = int.from_bytes(header[0x10:0x14], 'little')
        self.width    = int.from_bytes(header[0x18:0x1a], 'little')
        self.height   = int.from_bytes(header[0x1a:0x1c], 'little')
        logger.info(f'Processed header: {self.width}x{self.height} pixels, {self.n_frames} frames.')

        # This takes a few seconds on large files but helps us to identify bugs quickly
        self._sanity_check()

    def _sanity_check(self) -> None:
        # We walk through the file, making sure that we end up with the correct
        # number of frames. If this sanity check fails, we did not manage to
        # properly extract frames from the PXL container, which would indicate a bug.
        original_cursor_pos = self.fh.tell()
        counter = 0
        while True:
            self.fh.read(5 + 2) # Timestamp and tag
            block_size = int.from_bytes(self.fh.read(4), 'little')
            frame = self.fh.read(block_size)
            if not frame: break
            counter += 1
        if counter == self.n_frames:
            logger.info(f'Sanity check was successful, {self.n_frames} frames found.')
            self.fh.seek(original_cursor_pos) # Restore position
            return

        raise RuntimeError(f'Sanity check failed! {counter} frames found but {self.n_frames} expected.')

    def __iter__(self) -> Iterator[pxl_frame]:
        self.fh.seek(0x45d) # Position cursor at start of payload
        return self

    def __next__(self) -> pxl_frame:
        # pxl_frame constructor is expected to increase cursor position to the next frame
        return pxl_frame(self.fh, self.width, self.height)
