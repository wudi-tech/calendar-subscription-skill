import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from icalendar import Calendar
from test_feed import ROOT, sample

SCRIPTS = ROOT / 'skills/publish-calendar-feed/scripts'
SCRIPT = SCRIPTS / 'build_calendar.py'
sys.path.insert(0, str(SCRIPTS))

LEGACY = b'''BEGIN:VCALENDAR\r
VERSION:2.0\r
PRODID:-//Legacy//EN\r
BEGIN:VTIMEZONE\r
TZID:Asia/Shanghai\r
BEGIN:STANDARD\r
DTSTART:19700101T000000\r
TZOFFSETFROM:+0800\r
TZOFFSETTO:+0800\r
END:STANDARD\r
END:VTIMEZONE\r
BEGIN:VEVENT\r
UID:existing-series@example.invalid\r
DTSTAMP:20260101T000000Z\r
DTSTART;TZID=Asia/Shanghai:20300108T090000\r
DTEND;TZID=Asia/Shanghai:20300108T100000\r
RRULE:FREQ=WEEKLY;COUNT=4\r
SUMMARY:Existing series\r
BEGIN:VALARM\r
ACTION:DISPLAY\r
TRIGGER:-PT10M\r
DESCRIPTION:Reminder\r
END:VALARM\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:existing-series@example.invalid\r
DTSTAMP:20260102T000000Z\r
RECURRENCE-ID;TZID=Asia/Shanghai:20300115T090000\r
DTSTART;TZID=Asia/Shanghai:20300115T100000\r
DTEND;TZID=Asia/Shanghai:20300115T110000\r
SUMMARY:Moved occurrence\r
END:VEVENT\r
END:VCALENDAR\r
'''


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.exists(), 'Multi-source builder is not implemented yet')
        spec = importlib.util.spec_from_file_location('build_calendar', SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temporary = tempfile.TemporaryDirectory(prefix='calendar merge ')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.manifest = self.root / 'calendar.json'
        self.data = {'calendar_name': 'Combined calendar', 'sources': [
            {'id': 'study', 'path': 'study.json', 'format': 'json'},
            {'id': 'thesis', 'path': 'thesis.json', 'format': 'json'},
            {'id': 'legacy', 'path': 'legacy.ics', 'format': 'ics'},
        ]}
        study, thesis = sample(), sample()
        thesis['feed_id'] = 'thesis-demo'
        (self.root / 'study.json').write_text(json.dumps(study), encoding='utf-8')
        (self.root / 'thesis.json').write_text(json.dumps(thesis), encoding='utf-8')
        (self.root / 'legacy.ics').write_bytes(LEGACY)
        self.save()

    def save(self):
        self.manifest.write_text(json.dumps(self.data), encoding='utf-8')

    def build(self):
        return self.module.build_calendar(self.manifest)

    def test_multiple_sources_preserve_namespaces_and_existing_components(self):
        content = self.build()
        calendar = Calendar.from_ical(content)
        events = calendar.walk('VEVENT')
        self.assertEqual(len(events), 4)
        original = Calendar.from_ical(LEGACY)
        old_components = [component.to_ical() for component in original.subcomponents]
        merged_components = [component.to_ical() for component in calendar.subcomponents]
        for component in old_components:
            self.assertIn(component, merged_components)
        json_uids = [str(event['uid']) for event in events if '@calendar-subscription.invalid' in str(event['uid'])]
        self.assertEqual(len(set(json_uids)), 2)
        from build_feed import build_feed
        single_uid = str(Calendar.from_ical(build_feed(sample())).walk('VEVENT')[0]['uid'])
        self.assertIn(single_uid, json_uids)
        self.assertEqual(content, self.build())

    def test_updating_one_source_leaves_other_sources_unchanged(self):
        before = Calendar.from_ical(self.build()).walk('VEVENT')
        source = self.root / 'thesis.json'
        data = json.loads(source.read_text())
        data['events'][0].update(title='Thesis changed', sequence=1, updated_at='2030-01-02T12:00:00+08:00')
        source.write_text(json.dumps(data), encoding='utf-8')
        after = Calendar.from_ical(self.build()).walk('VEVENT')
        before_map = {(str(event['uid']), str(event.get('recurrence-id', ''))): event.to_ical() for event in before}
        after_map = {(str(event['uid']), str(event.get('recurrence-id', ''))): event.to_ical() for event in after}
        self.assertEqual(before_map.keys(), after_map.keys())
        self.assertEqual(sum(before_map[key] != after_map[key] for key in before_map), 1)

    def test_doubled_windows_carriage_returns_are_normalized_on_read(self):
        source = self.root / 'legacy.ics'
        old_bytes = LEGACY.replace(b'\r\n', b'\r\r\n')
        source.write_bytes(old_bytes)
        calendar = Calendar.from_ical(self.build())
        components = {component.to_ical() for component in calendar.subcomponents}
        for component in Calendar.from_ical(LEGACY).subcomponents:
            self.assertIn(component.to_ical(), components)
        self.assertEqual(source.read_bytes(), old_bytes)

    def test_manifest_reordering_does_not_change_output(self):
        before = self.build()
        self.data['sources'].reverse()
        self.save()
        self.assertEqual(self.build(), before)

    def test_existing_all_day_event_is_preserved(self):
        payload = b'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:all-day@example.invalid\r\nDTSTAMP:20300101T000000Z\r\nDTSTART;VALUE=DATE:20300109\r\nDTEND;VALUE=DATE:20300110\r\nSUMMARY:All-day legacy\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n'
        (self.root / 'all-day.ics').write_bytes(payload)
        self.data['sources'].append({'id': 'all-day', 'path': 'all-day.ics', 'format': 'ics'})
        self.save()
        merged = Calendar.from_ical(self.build())
        original = Calendar.from_ical(payload).walk('VEVENT')[0]
        event = next(item for item in merged.walk('VEVENT') if str(item['uid']) == 'all-day@example.invalid')
        self.assertEqual(event.to_ical(), original.to_ical())

    def test_collision_missing_and_disabled_sources(self):
        (self.root / 'thesis.json').write_bytes((self.root / 'study.json').read_bytes())
        with self.assertRaises(ValueError):
            self.build()
        self.data['sources'][1]['enabled'] = False
        (self.root / 'thesis.json').unlink()
        self.save()
        self.assertEqual(len(Calendar.from_ical(self.build()).walk('VEVENT')), 3)
        self.data['sources'][1]['enabled'] = True
        self.save()
        with self.assertRaises((ValueError, OSError)):
            self.build()

    def test_duplicate_source_path_source_id_and_namespace_are_rejected(self):
        original = copy.deepcopy(self.data)
        for change in ['path', 'id', 'namespace']:
            self.data = copy.deepcopy(original)
            if change == 'namespace':
                data = sample()
                data['events'][0]['id'] = 'another-event'
                (self.root / 'thesis.json').write_text(json.dumps(data), encoding='utf-8')
            else:
                self.data['sources'][1][change] = self.data['sources'][0][change]
            self.save()
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.build()

    def test_source_paths_cannot_escape_manifest_root(self):
        for path in ['../outside.json', str(self.root / 'study.json'), 'https://example.invalid/calendar.ics']:
            self.data['sources'][0]['path'] = path
            self.save()
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.build()

    def test_malformed_empty_and_unsupported_components_are_rejected(self):
        for content in [b'<html>not a calendar</html>',
                        b'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n',
                        b'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VTODO\r\nUID:todo\r\nEND:VTODO\r\nEND:VCALENDAR\r\n']:
            self.data['sources'] = [{'id': 'legacy', 'path': 'legacy.ics', 'format': 'ics'}]
            self.save()
            (self.root / 'legacy.ics').write_bytes(content)
            with self.subTest(content=content), self.assertRaises(ValueError):
                self.build()

    def test_conflicting_timezone_and_duplicate_event_are_rejected(self):
        self.data['sources'].append({'id': 'other', 'path': 'other.ics', 'format': 'ics'})
        self.save()
        (self.root / 'other.ics').write_bytes(LEGACY)
        with self.assertRaises(ValueError):
            self.build()
        changed = LEGACY.replace(b'UID:existing-series', b'UID:another-series').replace(b'TZOFFSETTO:+0800', b'TZOFFSETTO:+0900')
        (self.root / 'other.ics').write_bytes(changed)
        with self.assertRaises(ValueError):
            self.build()

    def test_cli_idempotence_failure_and_source_overwrite_protection(self):
        output = self.root / 'result.ics'
        command = [sys.executable, str(SCRIPT), '--manifest', str(self.manifest)]
        checked = subprocess.run(command + ['--check'], capture_output=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        for _ in range(2):
            result = subprocess.run(command + ['--output', str(output)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            if _ == 0:
                before = (output.read_bytes(), output.stat().st_mtime_ns)
        self.assertEqual((output.read_bytes(), output.stat().st_mtime_ns), before)
        collision = subprocess.run(command + ['--output', str(self.root / 'legacy.ics')], capture_output=True)
        self.assertNotEqual(collision.returncode, 0)
        self.assertEqual((self.root / 'legacy.ics').read_bytes(), LEGACY)
        (self.root / 'study.json').write_text('{}', encoding='utf-8')
        failed = subprocess.run(command + ['--output', str(output)], capture_output=True)
        self.assertNotEqual(failed.returncode, 0)
        self.assertEqual(output.read_bytes(), before[0])


if __name__ == '__main__':
    unittest.main()
