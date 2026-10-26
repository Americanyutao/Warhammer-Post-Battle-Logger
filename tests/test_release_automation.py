import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

P=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(P/'src'),str(P/'tools')]
import prepare_github_release as release
from package_update import package_release
from version import VERSION

class ReleaseAutomationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);app=self.root/'app';(app/'_internal').mkdir(parents=True)
        (app/'WH3BattleLogger.exe').write_bytes(b'app')
        (app/'_internal/python313.dll').write_bytes(b'runtime')
        self.output=self.root/'publish';package_release(app,self.output)
        self.tag='v'+VERSION;self.repository='owner/logger'
    def test_new_tag_creates_draft_with_both_assets(self):
        with patch('prepare_github_release.gh',side_effect=['[]','']) as gh:
            release.prepare_release(self.tag,self.output,self.repository)
        args=gh.call_args_list[1].args
        self.assertEqual(args[:3],('release','create',self.tag))
        self.assertIn('--draft',args);self.assertIn('--verify-tag',args)
        self.assertIn(str(self.output/release.ARCHIVE),args)
        self.assertIn(str(self.output/release.MANIFEST),args)
    def test_retry_updates_only_draft_assets(self):
        record=json.dumps([dict(tagName=self.tag,isDraft=True)])
        with patch('prepare_github_release.gh',side_effect=[record,'']) as gh:
            release.prepare_release(self.tag,self.output,self.repository)
        args=gh.call_args_list[1].args
        self.assertEqual(args[:3],('release','upload',self.tag));self.assertIn('--clobber',args)
    def test_published_release_is_not_modified(self):
        record=json.dumps([dict(tagName=self.tag,isDraft=False)])
        with patch('prepare_github_release.gh',return_value=record) as gh:
            with self.assertRaisesRegex(ValueError,'already published'):release.prepare_release(self.tag,self.output,self.repository)
        self.assertEqual(gh.call_count,1)
    def test_mismatched_tag_and_manifest_fail_before_any_upload(self):
        with patch('prepare_github_release.gh') as gh:
            with self.assertRaises(ValueError):release.prepare_release('v0.0.1',self.output,self.repository)
            path=self.output/release.MANIFEST
            data=json.loads(gzip.decompress(path.read_bytes()));data['version']='0.0.1'
            path.write_bytes(gzip.compress(json.dumps(data).encode()))
            with self.assertRaises(ValueError):release.prepare_release(self.tag,self.output,self.repository)
            gh.assert_not_called()
    def test_invalid_tag_is_rejected(self):
        for tag in ('latest','v1.2.3-beta','v1.2','refs/tags/'+self.tag):
            with self.subTest(tag=tag),self.assertRaises(ValueError):release.validate_tag(tag)

    def test_manual_release_can_use_manifest_from_older_tag(self):
        manifest=self.output/release.MANIFEST
        data=json.loads(gzip.decompress(manifest.read_bytes()));data['version']='1.0.5'
        manifest.write_bytes(gzip.compress(json.dumps(data).encode()))
        with patch('prepare_github_release.gh',side_effect=['[]','']) as gh:
            release.prepare_release('v1.0.5',self.output,self.repository)
        self.assertEqual(gh.call_args_list[1].args[:3],('release','create','v1.0.5'))

if __name__=='__main__':unittest.main()
