"""Compressed authenticated streaming logs. Key is separate from the log."""
import json
import os
from pathlib import Path
import struct
import zlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

MAGIC = b'WH3LOG02'
MAX_CHUNK = 8 * 1024 * 1024


def file_cipher(key, salt):
    derived = HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=MAGIC).derive(key)
    return AESGCM(derived)


def load_key(path, create=False):
    path = Path(path)
    if not path.exists() and create:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open('xb') as stream: stream.write(os.urandom(32))
        except FileExistsError:
            pass
    key = path.read_bytes()
    if len(key) != 32: raise ValueError('Invalid logger key: expected 32 bytes.')
    return key


class LogWriter:
    def __init__(self, path, key, metadata):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open('xb')
        self.salt = os.urandom(16)
        self.cipher = file_cipher(key, self.salt)
        self.header = MAGIC + self.salt
        self.stream.write(self.header)
        self.sequence, self.previous, self.closed = 0, b'', False
        self.write(dict(kind='header', schema=1, metadata=metadata))

    def write(self, record):
        if self.closed: raise ValueError('Log is closed.')
        raw = json.dumps(record, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
        if len(raw) > MAX_CHUNK: raise ValueError('Sample exceeds log limit.')
        sequence = struct.pack('>Q', self.sequence)
        data = self.cipher.encrypt(b'\0'*4 + sequence, zlib.compress(raw, 1), self.header + sequence + self.previous)
        self.stream.write(struct.pack('<I', len(data)))
        self.stream.write(data)
        self.previous = data[-16:]
        self.sequence += 1

    def flush(self):
        self.stream.flush()

    def close(self, summary):
        if self.closed: return
        try:
            self.write(dict(kind='footer', summary=summary))
            self.flush()
        finally:
            self.closed = True
            self.stream.close()


def read_log(path, key):
    """Reject damaged, reordered, truncated and wrong-key logs."""
    with Path(path).open('rb') as stream:
        header = stream.read(24)
        if len(header) != 24 or header[:8] != MAGIC: raise ValueError('Not a supported WH3 logger file.')
        cipher, previous, sequence, finished = file_cipher(key, header[8:]), b'', 0, False
        while True:
            length = stream.read(4)
            if not length: break
            if finished or len(length) != 4: raise ValueError('Damaged log framing.')
            size = struct.unpack('<I', length)[0]
            if not 16 <= size <= MAX_CHUNK: raise ValueError('Invalid encrypted chunk size.')
            data = stream.read(size)
            if len(data) != size: raise ValueError('Truncated logger file.')
            seq = struct.pack('>Q', sequence)
            packed = cipher.decrypt(b'\0'*4 + seq, data, header + seq + previous)
            decoder = zlib.decompressobj()
            raw = decoder.decompress(packed, MAX_CHUNK + 1)
            if len(raw) > MAX_CHUNK or not decoder.eof or decoder.unused_data:
                raise ValueError('Invalid compressed sample.')
            record = json.loads(raw)
            if sequence == 0 and record.get('kind') != 'header': raise ValueError('Missing header.')
            previous, sequence = data[-16:], sequence + 1
            finished = record.get('kind') == 'footer'
            yield record
        if not finished: raise ValueError('Log is incomplete: no authenticated footer.')
