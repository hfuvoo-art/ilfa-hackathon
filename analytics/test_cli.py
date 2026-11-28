"""Проверка пользовательских команд на временной синтетической SQLite."""

import csv
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from analytics.demo_data import create_demo_db


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.database = self.directory / 'synthetic.db'
        source = create_demo_db()
        target = sqlite3.connect(self.database)
        try:
            source.backup(target)
        finally:
            source.close()
            target.close()
        self.env = dict(os.environ, DATABASE_URL=f'sqlite:///{self.database}')
        self.root = Path(__file__).resolve().parents[1]

    def run_module(self, name, *args):
        return subprocess.run([sys.executable, '-m', name, *args], cwd=self.root,
                              env=self.env, text=True, capture_output=True, timeout=60)

    def test_segments_command_then_services_json_and_csv(self):
        result = self.run_module('analytics.segments')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Пациентов обработано: 5', result.stdout)
        result = self.run_module('analytics.services')
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['totals']['revenue'], 10000)
        self.assertTrue(report['reconciliation']['items_match_visits'])
        self.assertNotIn('patient_id', result.stdout)
        result = self.run_module('analytics.services', '--transitions-csv')
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = list(csv.DictReader(io.StringIO(result.stdout)))
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['from_category'], rows[0]['to_category'], rows[0]['n_transitions']),
                         ('Гигиена', 'Гигиена', '1'))

    def test_demo_html_contains_eight_figures(self):
        output = self.directory / 'demo.html'
        result = self.run_module('analytics.charts', '--output', str(output))
        self.assertEqual(result.returncode, 0, result.stderr)
        html = output.read_text(encoding='utf-8')
        self.assertIn('Все данные вымышлены', html)
        self.assertEqual(html.count('class="plotly-graph-div"'), 8)
        self.assertNotIn('<script src=', html)

    def test_missing_schema_returns_error_without_traceback(self):
        self.env['DATABASE_URL'] = 'sqlite://'
        for name in ('analytics.segments', 'analytics.services'):
            with self.subTest(module=name):
                result = self.run_module(name)
                self.assertEqual(result.returncode, 1)
                self.assertIn('Проверьте DATABASE_URL', result.stderr)
                self.assertNotIn('Traceback', result.stderr)

    def test_services_report_does_not_change_database(self):
        before = self.database.read_bytes()
        result = self.run_module('analytics.services')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.database.read_bytes(), before)
