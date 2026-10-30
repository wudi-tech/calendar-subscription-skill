import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from test_feed import ROOT, sample

PUBLISHER = ROOT / 'skills/publish-calendar-feed/scripts/Publish-Feed.ps1'
SHELL = shutil.which('powershell.exe') or shutil.which('pwsh')


@unittest.skipUnless(SHELL and shutil.which('git'), 'PowerShell and Git are required')
class PublisherTests(unittest.TestCase):
    def run_command(self, *command, cwd=None):
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout.strip()

    def setUp(self):
        self.assertTrue(PUBLISHER.exists(), 'Reusable publisher is not implemented yet')
        self.temporary = tempfile.TemporaryDirectory(prefix='calendar test ')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.remote = self.root / 'remote.git'
        self.repo = self.root / 'publish checkout'
        self.run_command('git', 'init', '--bare', '--initial-branch=main', str(self.remote))
        self.run_command('git', 'clone', str(self.remote), str(self.repo))
        self.run_command('git', 'config', 'user.name', 'Calendar Test', cwd=self.repo)
        self.run_command('git', 'config', 'user.email', 'calendar@example.invalid', cwd=self.repo)
        self.run_command('git', 'config', 'core.autocrlf', 'true', cwd=self.repo)
        (self.repo / '.nojekyll').write_text('', encoding='utf-8')
        self.run_command('git', 'add', '.nojekyll', cwd=self.repo)
        self.run_command('git', 'commit', '-m', 'Initialize', cwd=self.repo)
        self.run_command('git', 'push', '-u', 'origin', 'main', cwd=self.repo)
        self.source = self.root / 'events.json'
        self.source.write_text(json.dumps(sample()), encoding='utf-8')
        self.command = [SHELL, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(PUBLISHER),
                        '-Python', sys.executable, '-InputPath', str(self.source), '-PublishRepo', str(self.repo)]

    def invoke(self, publish=True):
        return subprocess.run(self.command + (['-Publish'] if publish else []),
                              capture_output=True, text=True, encoding='utf-8', errors='replace')

    def test_publication_is_idempotent_and_retries_pending_feed_commit(self):
        first = self.invoke()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        head = self.run_command('git', 'rev-parse', 'HEAD', cwd=self.repo)
        self.assertEqual(head, self.run_command('git', '--git-dir', str(self.remote), 'rev-parse', 'main'))
        self.assertIn('BEGIN:VCALENDAR', self.run_command('git', '--git-dir', str(self.remote), 'show', 'main:study-plan.ics'))
        published = subprocess.run(['git', '--git-dir', str(self.remote), 'show', 'main:study-plan.ics'],
                                   capture_output=True, check=True).stdout
        self.assertEqual(published, (self.repo / 'study-plan.ics').read_bytes())
        second = self.invoke()
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(head, self.run_command('git', 'rev-parse', 'HEAD', cwd=self.repo))
        data = sample()
        data['events'][0].update(title='Changed', sequence=1, updated_at='2030-01-02T12:00:00+08:00')
        self.source.write_text(json.dumps(data), encoding='utf-8')
        self.run_command(sys.executable, str(ROOT / 'skills/publish-calendar-feed/scripts/build_feed.py'),
                         '--input', str(self.source), '--output', str(self.repo / 'study-plan.ics'))
        self.run_command('git', '-c', 'core.autocrlf=false', 'add', 'study-plan.ics', cwd=self.repo)
        self.run_command('git', 'commit', '-m', 'Previously failed push', cwd=self.repo)
        pending = self.run_command('git', 'rev-parse', 'HEAD', cwd=self.repo)
        retried = self.invoke()
        self.assertEqual(retried.returncode, 0, retried.stdout + retried.stderr)
        self.assertEqual(pending, self.run_command('git', '--git-dir', str(self.remote), 'rev-parse', 'main'))

    def test_dirty_checkout_is_rejected_before_generation(self):
        (self.repo / 'unrelated.txt').write_text('Leave untouched', encoding='utf-8')
        failed = self.invoke()
        self.assertNotEqual(failed.returncode, 0)
        self.assertFalse((self.repo / 'study-plan.ics').exists())
        self.assertEqual((self.repo / 'unrelated.txt').read_text(), 'Leave untouched')

    def test_default_generates_without_committing(self):
        head = self.run_command('git', 'rev-parse', 'HEAD', cwd=self.repo)
        generated = self.invoke(publish=False)
        self.assertEqual(generated.returncode, 0, generated.stdout + generated.stderr)
        self.assertTrue((self.repo / 'study-plan.ics').exists())
        self.assertEqual(head, self.run_command('git', 'rev-parse', 'HEAD', cwd=self.repo))

    def test_unrelated_unpushed_commits_are_rejected(self):
        (self.repo / 'unrelated.txt').write_text('Local commit', encoding='utf-8')
        self.run_command('git', 'add', 'unrelated.txt', cwd=self.repo)
        self.run_command('git', 'commit', '-m', 'Unrelated local work', cwd=self.repo)
        failed = self.invoke()
        self.assertNotEqual(failed.returncode, 0)
        self.assertFalse((self.repo / 'study-plan.ics').exists())

    def test_manifest_mode_publishes_existing_and_new_sources(self):
        from icalendar import Calendar
        from test_merge import LEGACY
        (self.root / 'legacy.ics').write_bytes(LEGACY)
        manifest = self.root / 'calendar.json'
        manifest.write_text(json.dumps({'calendar_name': 'Combined', 'sources': [
            {'id': 'study', 'path': 'events.json', 'format': 'json'},
            {'id': 'legacy', 'path': 'legacy.ics', 'format': 'ics'},
        ]}), encoding='utf-8')
        self.command[self.command.index('-InputPath')] = '-ManifestPath'
        self.command[self.command.index(str(self.source))] = str(manifest)
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        published = subprocess.run(['git', '--git-dir', str(self.remote), 'show', 'main:study-plan.ics'],
                                   capture_output=True, check=True).stdout
        events = Calendar.from_ical(published).walk('VEVENT')
        self.assertEqual(len(events), 3)
        self.assertEqual(sum(str(event['uid']) == 'existing-series@example.invalid' for event in events), 2)

    def test_single_and_manifest_parameters_are_mutually_exclusive(self):
        failed = subprocess.run(self.command + ['-ManifestPath', str(self.source)], capture_output=True)
        self.assertNotEqual(failed.returncode, 0)
        self.assertFalse((self.repo / 'study-plan.ics').exists())


if __name__ == '__main__':
    unittest.main()
