"""Bounded, block-aligned Zstandard packets for WH3LOG03."""
from pathlib import Path
import struct
import sys
try:
    import zstandard as zstd
except ModuleNotFoundError:
    if getattr(sys,'frozen',False):raise
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'build/embedded-viewer-deps'))
    import zstandard as zstd

MAX_RAW=8*1024*1024
MAX_PACKET=MAX_RAW+65536+21
MAX_HISTORY=2*1024*1024
BLOCK_RECORDS=30
ENVELOPE=struct.Struct('<BI')
RESET=1
END=2


class Encoder:
    def __init__(self):self.compressor=None;self.count=0

    def pack(self,raw,final=False):
        if not 0<len(raw)<=MAX_RAW:raise ValueError('Sample exceeds log limit.')
        flags=0
        if self.compressor is None:
            self.compressor=zstd.ZstdCompressor(level=3,write_checksum=False,write_content_size=False,write_dict_id=False).compressobj()
            self.count=0;flags|=RESET
        self.count+=1
        final=final or self.count==BLOCK_RECORDS
        packed=self.compressor.compress(raw)+self.compressor.flush(zstd.COMPRESSOBJ_FLUSH_FINISH if final else zstd.COMPRESSOBJ_FLUSH_BLOCK)
        if final:flags|=END;self.compressor=None
        return ENVELOPE.pack(flags,len(raw))+packed


class LimitedOutput:
    def __init__(self):self.data=bytearray();self.limit=0
    def write(self,data):
        if len(self.data)+len(data)>self.limit:raise ValueError('Decompressed sample exceeds its declared size.')
        self.data.extend(data)
        return len(data)


class Decoder:
    def __init__(self):self.writer=None;self.output=LimitedOutput();self.count=0;self.block_limit=131072

    def unpack(self,packet):
        if len(packet)<ENVELOPE.size:raise ValueError('Truncated compressed sample envelope.')
        flags,size=ENVELOPE.unpack_from(packet);payload=packet[ENVELOPE.size:]
        if flags&~3 or not 0<size<=MAX_RAW:raise ValueError('Invalid compressed sample envelope.')
        reset=bool(flags&RESET);end=bool(flags&END)
        if reset!=(self.writer is None):raise ValueError('Invalid compression checkpoint order.')
        try:
            offset=0
            if reset:
                parameters=zstd.get_frame_parameters(payload)
                if parameters.dict_id or parameters.has_checksum or not 0<parameters.window_size<=MAX_HISTORY:
                    raise ValueError('Invalid compression history window.')
                self.block_limit=min(131072,parameters.window_size)
                offset=zstd.frame_header_size(payload)
                # Feed one complete block per call, with room for its full output.
                # Feeding multiple blocks at once can leave output pending after
                # the last compressed byte is consumed in python-zstandard 0.25.
                self.writer=zstd.ZstdDecompressor(max_window_size=MAX_HISTORY).stream_writer(self.output,write_size=131072,closefd=False)
                self.count=0
            self.count+=1
            if self.count>BLOCK_RECORDS or (self.count==BLOCK_RECORDS and not end):raise ValueError('Compression checkpoint exceeds record limit.')
            self.output.data=bytearray();self.output.limit=size
            # Flush packets end on complete Zstd blocks. Validate the frame end
            # without an unbounded decompression allocation or a second decode.
            last=False;blocks=0;block_start=0
            while offset<len(payload):
                if last or len(payload)-offset<3:raise ValueError('Invalid Zstandard block boundary.')
                header=int.from_bytes(payload[offset:offset+3],'little');offset+=3
                last=bool(header&1);kind=(header>>1)&3;length=header>>3
                if kind==3 or length>self.block_limit:raise ValueError('Invalid Zstandard block size.')
                offset+=1 if kind==1 else length
                if offset>len(payload):raise ValueError('Truncated Zstandard block.')
                chunk=payload[block_start:offset]
                if self.writer.write(chunk)!=len(chunk):raise ValueError('Compressed block was not consumed.')
                blocks+=1;block_start=offset
            if not blocks or last!=end:raise ValueError('Invalid Zstandard frame end.')
            if len(self.output.data)!=size:
                raise ValueError('Decompressed sample size does not match its envelope.')
            raw=bytes(self.output.data)
            if end:self.writer.close();self.writer=None
            return raw,end
        except zstd.ZstdError as error:raise ValueError('Invalid compressed sample: '+str(error)) from error

    def close(self):
        if self.writer:self.writer.close();self.writer=None
