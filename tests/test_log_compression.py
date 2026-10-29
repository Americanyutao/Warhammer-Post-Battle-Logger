import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'src'))
from logfile import LogWriter,read_log,log_version,load_key
from log_codec import Encoder,Decoder,ENVELOPE,RESET,END,MAX_RAW,MAX_HISTORY,zstd
from log_migration import migrate_log,optimize_captures,CaptureMaintenance


class CompressionTests(unittest.TestCase):
    def test_all_values_and_samples_round_trip_across_checkpoints(self):
        records=[dict(kind='sample',sim_s=i,units=[dict(id='é',unknown=None,zero=0,flag=True,integer=1,
            negative_zero=-0.0,precise=1.23456789012345,empty=[],extra={'future':[1,False,None]})]) for i in range(91)]
        with tempfile.TemporaryDirectory() as d:
            decoded=[]
            for version in (2,3):
                path=Path(d)/f'{version}.wh3log';writer=LogWriter(path,bytes(32),{'custom':'retained'},format_version=version)
                for record in records:writer.write(record)
                writer.close({'reason':'test'})
                decoded.append(list(read_log(path,bytes(32))))
                self.assertEqual(log_version(path),version)
            self.assertEqual(json.dumps(decoded[0]),json.dumps(decoded[1]))
            self.assertEqual(len(decoded[1]),93)

    def test_each_flushed_record_is_recoverable_without_waiting_for_frame_end(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'partial.wh3log';writer=LogWriter(path,bytes(32),{})
            try:
                for i in range(33):
                    writer.write(dict(kind='sample',sim_s=i,units=[]));writer.flush(durable=True)
                    records=list(read_log(path,bytes(32),recover_tail=True))
                    self.assertEqual(len(records),i+2);self.assertEqual(records[-1]['sim_s'],i)
            finally:writer.stream.close()
            with self.assertRaises(ValueError):list(read_log(path,bytes(32)))

    def test_compression_happens_before_authenticated_encryption(self):
        with tempfile.TemporaryDirectory() as d:
            writer=LogWriter(Path(d)/'test.wh3log',bytes(32),{})
            cipher=writer.cipher
            with patch.object(writer,'cipher',wraps=cipher) as encrypted:
                record=dict(kind='sample',units=[{'same':'x'*2000}]*40)
                writer.write(record);packet=encrypted.encrypt.call_args.args[1]
                self.assertLess(len(packet),1000)
                self.assertEqual(ENVELOPE.unpack_from(packet)[1],len(json.dumps(record,separators=(',',':')).encode()))
                writer.close({})

    def test_truncated_packet_recovers_only_authenticated_prefix(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'test.wh3log';writer=LogWriter(path,bytes(32),{})
            writer.write(dict(kind='sample',sim_s=1,units=[]));writer.close({})
            path.write_bytes(path.read_bytes()[:-7])
            self.assertEqual(len(list(read_log(path,bytes(32),recover_tail=True))),2)
            with self.assertRaises(ValueError):list(read_log(path,bytes(32)))

    def test_invalid_declared_size_is_bounded_and_rejected(self):
        for declared in (0,MAX_RAW+1,1,200001):
            encoder=Encoder();packet=encoder.pack(b'x'*200000,final=True)
            flags,size=ENVELOPE.unpack_from(packet)
            decoder=Decoder()
            try:
                with self.assertRaises(ValueError):decoder.unpack(ENVELOPE.pack(flags,declared)+packet[5:])
                self.assertLessEqual(len(decoder.output.data),max(0,min(declared,MAX_RAW)))
            finally:decoder.close()

    def test_large_samples_drain_every_block_before_next_record(self):
        encoder=Encoder();decoder=Decoder()
        try:
            for size in (65537,122597,131072,131073,500000,MAX_RAW):
                for raw in (b'x'*size,os.urandom(size)):
                    packet=encoder.pack(raw)
                    actual,ended=decoder.unpack(packet)
                    self.assertEqual(actual,raw)
            actual,ended=decoder.unpack(encoder.pack(b'footer',final=True))
            self.assertEqual(actual,b'footer');self.assertTrue(ended)
        finally:decoder.close()

    def test_frame_flags_bounds_and_trailing_bytes_are_validated(self):
        original=Encoder().pack(b'hello',final=True)
        flags,size=ENVELOPE.unpack_from(original)
        packets=[b'',ENVELOPE.pack(4,size)+original[5:],ENVELOPE.pack(END,size)+original[5:],
            ENVELOPE.pack(RESET,size)+original[5:],original+b'\0',original[:-1]]
        large=bytes.fromhex('28b52ffd0060290000')+b'hello' # Valid frame, 4 MiB window, one final raw block.
        self.assertGreater(zstd.get_frame_parameters(large).window_size,MAX_HISTORY)
        packets.append(ENVELOPE.pack(RESET|END,5)+large)
        for packet in packets:
            with self.subTest(packet=packet[:8]):
                decoder=Decoder()
                try:
                    with self.assertRaises(ValueError):decoder.unpack(packet)
                finally:decoder.close()


class MigrationTests(unittest.TestCase):
    def legacy(self,root,name='old.wh3log',complete=True):
        folder=Path(root)/'captures';key=load_key(folder/'logger.key',True);path=folder/name
        writer=LogWriter(path,key,dict(source='test',unchanged=None),format_version=2)
        for i in range(65):writer.write(dict(kind='sample',sim_s=i,units=[dict(id='a',known=5,unknown=None)]))
        if complete:writer.close({'reason':'original','bytes_before_footer':999})
        else:writer.stream.close()
        return path,key

    def test_atomic_migration_preserves_every_decoded_record_key_and_timestamp(self):
        with tempfile.TemporaryDirectory() as d:
            path,key=self.legacy(d);old=list(read_log(path,key));stamp=path.stat().st_mtime_ns;key_bytes=(path.parent/'logger.key').read_bytes()
            result=migrate_log(path,key)
            self.assertTrue(result['verified']);self.assertLess(result['after_bytes'],result['before_bytes'])
            self.assertEqual(log_version(path),3);self.assertEqual(list(read_log(path,key)),old)
            self.assertEqual(path.stat().st_mtime_ns,stamp);self.assertEqual((path.parent/'logger.key').read_bytes(),key_bytes)
            before=path.read_bytes();self.assertIsNone(migrate_log(path,key));self.assertEqual(path.read_bytes(),before)
            self.assertFalse(list(path.parent.glob('.*.migrating')))

    def test_incomplete_corrupt_and_wrong_key_files_are_left_unchanged(self):
        for kind in ('incomplete','corrupt','wrong-key'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as d:
                path,key=self.legacy(d,complete=kind!='incomplete')
                if kind=='corrupt':
                    data=bytearray(path.read_bytes());data[50]^=1;path.write_bytes(data)
                before=path.read_bytes()
                with self.assertRaises(Exception):migrate_log(path,b'x'*32 if kind=='wrong-key' else key)
                self.assertEqual(path.read_bytes(),before);self.assertFalse(list(path.parent.glob('.*.migrating')))

    def test_cancel_replace_failure_and_failed_verification_keep_original(self):
        for failure in ('cancel','replace','verification'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as d:
                path,key=self.legacy(d);before=path.read_bytes();stop=threading.Event()
                if failure=='cancel':stop.set()
                def altered(source,*args,**kwargs):
                    for record in read_log(source,*args,**kwargs):
                        if Path(source)!=path:record=dict(record,changed=True)
                        yield record
                from contextlib import nullcontext
                context=patch.object(Path,'replace',side_effect=PermissionError('in use')) if failure=='replace' else patch('log_migration.read_log',side_effect=altered) if failure=='verification' else nullcontext()
                with context,self.assertRaises(Exception):migrate_log(path,key,stop=stop)
                self.assertEqual(path.read_bytes(),before);self.assertFalse(list(path.parent.glob('.*.migrating')))

    def test_busy_files_are_skipped_and_no_key_is_created(self):
        with tempfile.TemporaryDirectory() as d:
            path,key=self.legacy(d);before=path.read_bytes()
            result=optimize_captures(d,busy=lambda:{path.resolve()})
            self.assertFalse(result['migrated']);self.assertEqual(path.read_bytes(),before)
            (path.parent/'logger.key').unlink()
            with self.assertRaises(FileNotFoundError):optimize_captures(d)
            self.assertFalse((path.parent/'logger.key').exists());self.assertEqual(path.read_bytes(),before)

    def test_startup_only_migrates_and_update_cleanup_is_limited_to_capture_html(self):
        with tempfile.TemporaryDirectory() as d:
            path,key=self.legacy(d);html=path.with_suffix('.html');html.write_text('old report')
            bundled=Path(d)/'_internal/src/report_template.html';bundled.parent.mkdir(parents=True);bundled.write_text('keep implementation')
            other=Path(d)/'notes.html';other.write_text('keep')
            result=optimize_captures(d);self.assertEqual(len(result['migrated']),1);self.assertTrue(html.exists())
            result=optimize_captures(d,delete_html=True)
            self.assertEqual(result['deleted_html'],['old.html']);self.assertFalse(html.exists())
            self.assertTrue(bundled.exists());self.assertTrue(other.exists())

    def test_background_queue_retains_update_cleanup_requested_during_migration(self):
        with tempfile.TemporaryDirectory() as d:
            started=threading.Event();release=threading.Event();calls=[]
            def optimize(*args,**kwargs):
                calls.append(kwargs['delete_html']);started.set();release.wait(5)
                return dict(migrated=[],skipped=[],deleted_html=[])
            maintenance=CaptureMaintenance(d)
            with patch('log_migration.optimize_captures',side_effect=optimize):
                try:
                    maintenance.start();self.assertTrue(started.wait(5));maintenance.start(delete_html=True);release.set()
                    maintenance.thread.join(5)
                finally:release.set();maintenance.stop()
            self.assertEqual(calls,[False,True])

    def test_fast_exit_still_applies_queued_update_cleanup(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)/'captures';folder.mkdir();html=folder/'old.html';html.write_text('old')
            maintenance=CaptureMaintenance(d);maintenance.pending=3;maintenance.stop()
            self.assertFalse(html.exists())


if __name__=='__main__':unittest.main()
