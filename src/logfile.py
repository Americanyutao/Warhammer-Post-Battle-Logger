"""Compressed authenticated streaming logs. Key is separate from the log."""
import json
import os
from pathlib import Path
import struct
import zlib
from log_codec import Encoder,Decoder,MAX_PACKET
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

LEGACY_MAGIC = b'WH3LOG02'
MAGIC = b'WH3LOG03'
MAX_CHUNK = 8 * 1024 * 1024


def file_cipher(key, salt, magic=MAGIC):
    derived = HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=magic).derive(key)
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


def log_version(path):
    with Path(path).open('rb') as stream:magic=stream.read(8)
    return 3 if magic==MAGIC else 2 if magic==LEGACY_MAGIC else None


class LogWriter:
    def __init__(self, path, key, metadata, *, format_version=3, header_record=None):
        if format_version not in (2,3):raise ValueError('Unsupported log version.')
        self.magic=MAGIC if format_version==3 else LEGACY_MAGIC
        self.encoder=Encoder() if format_version==3 else None
        self.footer_written=False
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open('xb')
        self.salt = os.urandom(16)
        self.cipher = file_cipher(key, self.salt,self.magic)
        self.header = self.magic + self.salt
        self.stream.write(self.header)
        self.sequence, self.previous, self.closed = 0, b'', False
        self.write(header_record if header_record is not None else dict(kind='header', schema=1, metadata=metadata))

    def write(self, record):
        if self.closed or self.footer_written: raise ValueError('Log is closed.')
        raw = json.dumps(record, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
        if len(raw) > MAX_CHUNK: raise ValueError('Sample exceeds log limit.')
        sequence = struct.pack('>Q', self.sequence)
        final=record.get('kind')=='footer'
        packed=self.encoder.pack(raw,final=final) if self.encoder else zlib.compress(raw,1)
        data = self.cipher.encrypt(b'\0'*4 + sequence, packed, self.header + sequence + self.previous)
        self.stream.write(struct.pack('<I', len(data)))
        self.stream.write(data)
        self.previous = data[-16:]
        self.sequence += 1
        self.footer_written=final

    def flush(self, *, durable=False):
        self.stream.flush()
        if durable: os.fsync(self.stream.fileno())

    def close(self, summary):
        if self.closed: return
        try:
            if not self.footer_written:self.write(dict(kind='footer', summary=summary))
            self.flush(durable=True)
        finally:
            self.closed = True
            self.stream.close()


def read_log(path, key, *, recover_tail=False, progress=None):
    """Reject damaged, reordered, truncated and wrong-key logs."""
    with Path(path).open('rb') as stream:
        total=os.fstat(stream.fileno()).st_size
        header = stream.read(24)
        if len(header) != 24 or header[:8] not in (MAGIC,LEGACY_MAGIC): raise ValueError('Not a supported WH3 logger file.')
        modern=header[:8]==MAGIC
        codec=Decoder() if modern else None
        cipher, previous, sequence, finished = file_cipher(key, header[8:],header[:8]), b'', 0, False
        try:
            while True:
                length = stream.read(4)
                if not length: break
                if finished: raise ValueError('Damaged log framing.')
                if len(length) != 4:
                    if recover_tail: break
                    raise ValueError('Damaged log framing.')
                size = struct.unpack('<I', length)[0]
                if not 16 <= size <= (MAX_PACKET if modern else MAX_CHUNK): raise ValueError('Invalid encrypted chunk size.')
                data = stream.read(size)
                if len(data) != size:
                    if recover_tail: break
                    raise ValueError('Truncated logger file.')
                seq = struct.pack('>Q', sequence)
                packed = cipher.decrypt(b'\0'*4 + seq, data, header + seq + previous)
                if modern:raw,ended=codec.unpack(packed)
                else:
                    decoder = zlib.decompressobj()
                    raw = decoder.decompress(packed, MAX_CHUNK + 1)
                    if len(raw) > MAX_CHUNK or not decoder.eof or decoder.unused_data:
                        raise ValueError('Invalid compressed sample.')
                record = json.loads(raw)
                if not isinstance(record,dict):raise ValueError('Invalid recording record.')
                if sequence == 0 and record.get('kind') != 'header': raise ValueError('Missing header.')
                previous, sequence = data[-16:], sequence + 1
                finished = record.get('kind') == 'footer'
                if modern and finished and not ended:raise ValueError('Footer does not end a compression frame.')
                if progress:progress(stream.tell(),total)
                yield record
            if not finished and not recover_tail: raise ValueError('Log is incomplete: no authenticated footer.')
        finally:
            if codec:codec.close()
