# PXL Frame Extractor (Experimental)

## Overview

This repository contains a small Python module for reading PXL files produced by [Biospacelab Photon Imagers](https://biospacelab.com/products/) and reconstructing their image frames without relying on the M3 Vision software GUI. The GUI does not expose an SDK, which makes automated processing and batch extraction cumbersome or impossible. With this module you can open a `.pxl` container, iterate through its frames, and materialize each frame as a NumPy array for downstream analysis, visualization, or export.

> **Disclaimer**  
> This toolkit is **experimental**. The file format description is inferred from observed data and the provided reader implementation; instruments and software versions may vary. Please verify results independently and use the outputs with care. The module itself logs a warning to emphasize this point.

## Installation and Usage

Install the package using pip:
```
pip install pxl-file-reader
```

You can then use `pxl_file()` to open the file and parse the header. This provides access to `width`, `height` and `n_frames` (i.e. frame dimensions and count). To access individual frames, iterate through the `pxl_file` instance as shown in the example below. Use ``frame.timestamp`` to access the time stamp in milliseconds, and ``frame.pixel_array`` to uncompress the frame and retrieve the frame as `numpy.ndarray`. Note that for performance reasons, decompression of frames is deferred until ``pixel_array`` is called. Access is **not** thread-safe!

```
from pxl_file_reader import pxl_file
from matplotlib import pyplot as plt

import logging
#logging.basicConfig(level=logging.DEBUG)
logging.basicConfig(level=logging.INFO)

pxl = pxl_file('longtime_experiment.pxl')
print(f'Image properties: {pxl.width}x{pxl.height} pixels, {pxl.n_frames} frames.')

# enumerate() used for convenience, you can also simply iterate with "for frame in pxl:"
for i, frame in enumerate(pxl):
    print(f'Frame {i} acquired at time stamp {frame.timestamp}')
    # Select and plot two frames
    if i == 10 or frame.timestamp == 71998459 or True:
        plt.imshow(frame.pixel_array, cmap='gray')
        plt.axis('off')
        plt.colorbar()
        plt.show()

```


## PXL file format (what we know so far) and implementation details

```
+-----------------------------------------------------------------------------------+
|                                    PXL FILE                                       |
+-----------------------------------------------------------------------------------+
|                                     HEADER                                        |
|                                                                                   |
|  Offset  Size  Description                                                        |
|  ------  ----  ----------------------------------------------------------------   |
|  0x0000  4     Magic: ASCII 'P','X','L',' '                                       |
|  0x0010  4     n_frames   (uint32_le)                                             |
|  0x0018  2     width      (uint16_le)                                             |
|  0x001A  2     height     (uint16_le)                                             |
|  ...          (additional/undocumented bytes; parser reads 0x45D bytes total)     |
|                                                                                   |
+-----------------------------------------------------------------------------------+
|                                 FRAME BLOCKS                                      |
+-----------------------------------------------------------------------------------+
|  Frame #0                                                                         |
|  +----------------+----------------+----------------+---------------------------+ |
|  | Timestamp(5 B) | Tag (2 B)      | BlockSize(4 B) | Payload (BlockSize bytes) | |
|  +----------------+----------------+----------------+---------------------------+ |
|                                                                                   |
|  Frame #1                                                                         |
|  +----------------+----------------+----------------+---------------------------+ |
|  | Timestamp(5 B) | Tag (2 B)      | BlockSize(4 B) | Payload (BlockSize bytes) | |
|  +----------------+----------------+----------------+---------------------------+ |
|                                                                                   |
|  ...                                                                              |
|                                                                                   |
|  Frame #N-1                                                                       |
|  +----------------+----------------+----------------+---------------------------+ |
|  | Timestamp(5 B) | Tag (2 B)      | BlockSize(4 B) | Payload (BlockSize bytes) | |
|  +----------------+----------------+----------------+---------------------------+ |
+-----------------------------------------------------------------------------------+
```

The current understanding of the format comes directly from inspection of real files. Everything is little‑endian. The container begins with a fixed header that includes a magic identifier, image geometry, a frame count and other data such as comments which are not processed by this toolkit. The header is followed by a stream of frame blocks. The parser consumes `0x45D` bytes as the header region and then iterates over frame records.

The header starts with the ASCII magic `PXL `. If this signature is missing, the parser aborts. Within the consumed header region, the implementation extracts three fields: the total number of frames at bytes `0x10:0x14` (four bytes, `uint32_le`), the image width at `0x18:0x1A` (two bytes, `uint16_le`), and the image height at `0x1A:0x1C` (two bytes, `uint16_le`).

Each frame block in the payload begins with a small container‑level preamble, followed by the frame’s pixel payload. The preamble comprises a 40‑bit timestamp (five bytes, little‑endian), a two‑byte tag whose purpose is presently unknown, and a four‑byte block size that gives the length in bytes of the ensuing payload. Milliseconds is a plausible unit for this timestamp. The reader stores the raw payload verbatim for each frame and defers pixel reconstruction to a property accessor. Since the frame decompression and reconstruction is a costly operation, this enables efficient processing of large files since frames are only decoded reconstructed upon request.

The pixel payload itself is a bit‑packed sparse row encoding designed to be compact when most pixels are zero. The decoder initializes a full `height × width` image with zeros and then overlays only the non‑zero events present in the stream. For each row that contains events, the payload first encodes a row record header of 22 bits: eleven bits for the row index and eleven bits for the count of non‑zero pixels in that row. It then follows with exactly `count` pairs of values, each pair consuming 23 bits: eleven bits for the column index and twelve bits for the pixel intensity. Pixels not mentioned in the stream remain zero. Values are read as twelve‑bit unsigned quantities and stored in a `numpy.int16` array; if your downstream tooling assumes a particular dynamic range or scaling, you may normalize or rescale accordingly. The decoder proceeds while at least twenty‑two bits remain; it logs errors if the stream ends prematurely or if any decoded coordinate falls outside the declared dimensions.

## Acknowledgments

This work has received funding from the European Union's Horizon Europe EIC 2023 Pathfinder Open program under grant agreement No 101129734.
