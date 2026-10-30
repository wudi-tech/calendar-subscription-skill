import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'skills/publish-calendar-feed/scripts/build_feed.py'


def sample():
    return {
        'feed_id': 'demo-study', 'calendar_name': '学习计划',
        'events': [{
            'id': 'german-lesson-001', 'title': '德语课',
            'start': '2030-01-08T09:00:00+08:00',
            'end': '2030-01-08T10:00:00+08:00',
            'updated_at': '2030-01-01T12:00:00+08:00',
            'sequence': 0, 'alarm_minutes': 10,
            'description': '阅读;听力,复习\\词汇\n第二行',
        }],
    }


class FeedTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.exists(), 'Reusable feed generator is not implemented yet')
        spec = importlib.util.spec_from_file_location('build_feed', SCRIPT)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def test_utc_alarm_escaping_and_crlf(self):
        result = self.mod.build_feed(sample())
        self.assertIn(b'DTSTART:20300108T010000Z\r\n', result)
        self.assertIn(b'TRIGGER:-PT10M\r\n', result)
        self.assertIn('DESCRIPTION:阅读\\;听力\\,复习\\\\词汇\\n第二行'.encode(), result)
        self.assertNotIn(b'\n', result.replace(b'\r\n', b''))
        self.assertTrue(result.endswith(b'END:VCALENDAR\r\n'))

    def test_update_preserves_uid_and_increases_explicit_revision(self):
        original = sample()
        changed = copy.deepcopy(original)
        changed['events'][0].update(title='改课', start='2030-01-08T10:00:00+08:00',
            end='2030-01-08T11:00:00+08:00', sequence=1,
            updated_at='2030-01-02T12:00:00+08:00')
        before = self.mod.build_feed(original).split(b'\r\n')
        after = self.mod.build_feed(changed).split(b'\r\n')
        self.assertEqual([x for x in before if x.startswith(b'UID:')],
                         [x for x in after if x.startswith(b'UID:')])
        self.assertIn(b'SEQUENCE:1', after)
        self.assertIn(b'LAST-MODIFIED:20300102T040000Z', after)
        self.assertEqual(self.mod.build_feed(changed), self.mod.build_feed(changed))

    def test_utf8_folding_never_splits_codepoints_or_exceeds_75_octets(self):
        data = sample()
        data['events'][0]['title'] = '中文日程😀' * 50
        result = self.mod.build_feed(data)
        for line in result.split(b'\r\n'):
            self.assertLessEqual(len(line), 75)
            line.decode('utf-8')
        unfolded = result.replace(b'\r\n ', b'')
        self.assertIn(('SUMMARY:' + data['events'][0]['title']).encode(), unfolded)

    def test_invalid_inputs_rejected(self):
        cases = []
        for field, value in [('start', '2030-01-08T09:00:00'),
                             ('end', '2030-01-08T08:00:00+08:00'),
                             ('sequence', -1), ('sequence', True),
                             ('alarm_minutes', -10), ('alarm_minutes', True),
                             ('status', 'UNKNOWN'), ('title', ''),
                             ('updated_at', 'not-a-date')]:
            data = sample()
            data['events'][0][field] = value
            cases.append(data)
        duplicate = sample()
        duplicate['events'].append(copy.deepcopy(duplicate['events'][0]))
        cases.append(duplicate)
        for data in cases:
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.mod.build_feed(data)

    def test_cancelled_event_keeps_uid_but_has_no_alarm(self):
        data = sample()
        uid = next(x for x in self.mod.build_feed(data).split(b'\r\n') if x.startswith(b'UID:'))
        data['events'][0].update(status='CANCELLED', sequence=1)
        result = self.mod.build_feed(data)
        self.assertIn(uid, result)
        self.assertIn(b'STATUS:CANCELLED', result)
        self.assertNotIn(b'BEGIN:VALARM', result)

    def test_unsupported_fields_are_not_silently_discarded(self):
        for field, value in [('uid', 'old@example.invalid'), ('rrule', 'FREQ=WEEKLY'), ('all_day', True)]:
            data = sample()
            data['events'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.mod.build_feed(data)

    def test_cli_is_idempotent_and_does_not_overwrite_on_error(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'events.json'
            output = Path(directory) / 'study-plan.ics'
            source.write_text(json.dumps(sample()), encoding='utf-8')
            command = [sys.executable, str(SCRIPT), '--input', str(source), '--output', str(output)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            content, modified = output.read_bytes(), output.stat().st_mtime_ns
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual((output.read_bytes(), output.stat().st_mtime_ns), (content, modified))
            data = sample()
            data['events'][0]['end'] = 'invalid'
            source.write_text(json.dumps(data), encoding='utf-8')
            failed = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(output.read_bytes(), content)

    def test_check_mode_and_source_collision(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'events.json'
            source.write_text(json.dumps(sample()), encoding='utf-8')
            command = [sys.executable, str(SCRIPT), '--input', str(source)]
            checked = subprocess.run(command + ['--check'], capture_output=True, text=True)
            self.assertEqual(checked.returncode, 0, checked.stderr)
            before = source.read_bytes()
            collision = subprocess.run(command + ['--output', str(source)], capture_output=True, text=True)
            self.assertNotEqual(collision.returncode, 0)
            self.assertEqual(source.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
