"""Run offline tests; leave desktop and local reference checks to Windows QA."""
from pathlib import Path
import sys
import unittest

P = Path(__file__).resolve().parents[1]
EXTERNAL = {
    'test_logger.NativeTests.test_both_profile_anchor_sets_match_their_executable': 'Requires locally installed game executables.',
    'test_logger.RateTests.test_ui_default_is_private_and_rates_are_slower_options': 'Requires an interactive Windows desktop.',
    'test_report_assets.ReportAssetsTests.test_full_original_library_is_kept_locally': 'Requires the original local game asset export.',
    'test_release.ReleaseTests.test_log_icon_loads_and_native_tray_has_no_visible_window': 'Requires an interactive Windows notification tray.',
}


def cases(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from cases(item)
        else:
            yield item


if __name__ == '__main__':
    (P / 'build').mkdir(exist_ok=True)
    suite = unittest.defaultTestLoader.discover(str(P / 'tests'))
    tests = list(cases(suite))
    ids = {test.id() for test in tests}
    missing = EXTERNAL.keys() - ids
    if missing:
        raise RuntimeError(f'Review outdated CI exclusions: {sorted(missing)}')
    for test in tests:
        if test.id() in EXTERNAL:
            # Mark only this instance, preserving the normal local test suite.
            method = getattr(test, test._testMethodName)
            setattr(test, test._testMethodName, unittest.skip(EXTERNAL[test.id()])(method))
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(tests))
    sys.exit(not result.wasSuccessful())

