from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml
from icalendar import Calendar
from test_feed import ROOT

SKILL = ROOT / 'skills/publish-calendar-feed'
TEMPLATE = SKILL / 'assets/github-actions/publish-calendar.yml'


class CloudWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(TEMPLATE.exists(), 'Opt-in Pages workflow template is not implemented yet')
        self.workflow = yaml.safe_load(TEMPLATE.read_text(encoding='utf-8'))

    def test_deployment_is_opt_in_and_depends_on_a_successful_build(self):
        self.assertIn('CALENDAR_CLOUD_PUBLISH', self.workflow['jobs']['build']['if'])
        self.assertIn("'true'", self.workflow['jobs']['build']['if'])
        self.assertIn('default_branch', self.workflow['jobs']['build']['if'])
        self.assertEqual(self.workflow['jobs']['deploy']['needs'], 'build')
        self.assertEqual(self.workflow['permissions'], {'contents': 'read'})
        self.assertEqual(self.workflow['jobs']['deploy']['permissions']['pages'], 'write')
        self.assertEqual(self.workflow['jobs']['deploy']['permissions']['id-token'], 'write')
        self.assertFalse(self.workflow['concurrency']['cancel-in-progress'])
        uploads = [step for step in self.workflow['jobs']['build']['steps'] if 'upload-pages-artifact' in step.get('uses', '')]
        self.assertEqual(uploads[0]['with']['path'], '${{ env.CALENDAR_SITE }}')
        site = self.workflow['jobs']['build']['env']['CALENDAR_SITE']
        self.assertIn('runner.temp', site)
        self.assertIn('github.run_id', site)

    def test_build_command_runs_with_sources_accessible_in_a_checkout(self):
        import shutil
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tools = root / 'tools/calendar'
            tools.mkdir(parents=True)
            for name in ['build_feed.py', 'build_calendar.py']:
                shutil.copy2(SKILL / 'scripts' / name, tools / name)
            shutil.copytree(SKILL / 'assets/multi-source', root / 'inputs')
            build = next(step for step in self.workflow['jobs']['build']['steps'] if step.get('id') == 'generate')
            # The same command is executed by the Ubuntu build job; only Python is resolved here.
            command = build['run'].split()
            self.assertEqual(command[:2], ['python', 'tools/calendar/build_calendar.py'])
            command[0] = sys.executable
            command[command.index('--manifest') + 1] = 'inputs/calendar.json'
            command[command.index('--output') + 1] = 'isolated-site/study-plan.ics'
            (root / '_site').mkdir()
            (root / '_site/unrelated-private.txt').write_text('Must not be published')
            result = subprocess.run(command, cwd=root, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            output = root / 'isolated-site/study-plan.ics'
            self.assertEqual([item.name for item in output.parent.iterdir()], ['study-plan.ics'])
            self.assertEqual(len(Calendar.from_ical(output.read_bytes()).walk('VEVENT')), 3)
            before = output.read_bytes()
            (root / 'inputs/sources/thesis.json').unlink()
            failed = subprocess.run(command, cwd=root, capture_output=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(output.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
