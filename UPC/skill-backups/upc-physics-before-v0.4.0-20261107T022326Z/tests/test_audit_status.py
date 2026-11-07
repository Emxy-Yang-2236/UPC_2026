"""Regression checks for file integrity versus unresolved scientific states."""
import unittest

from test_project_tools import ProjectToolTestCase, audit_module


class AuditStatusTests(ProjectToolTestCase):
    def setUp(self):
        super().setUp()
        self.complete_fixture()

    def test_complete_evidence_retains_success_and_empty_findings(self):
        result = audit_module.audit(self.project)
        self.assertTrue(result['ready'])
        self.assertTrue(result['integrity_ok'])
        self.assertEqual(result['integrity_errors'], [])
        self.assertEqual(result['status_findings'], [])

    def test_saved_unsuccessful_attempt_does_not_become_missing_file_or_pass(self):
        self.set_cell('runs', 'status', 'failed')
        result = audit_module.audit(self.project)
        self.assertFalse(result['ready'])
        self.assertTrue(result['integrity_ok'])
        self.assertEqual({r['table'] for r in result['status_findings']}, {'runs'})
        self.assertEqual(result['status_findings'][0]['status'], 'failed')
        self.assertEqual(self.cli('audit_project.py', self.project).returncode, 1)

    def test_a_passing_check_does_not_hide_an_additional_failed_check(self):
        checks = self.rows('validation')
        checks.append(dict(checks[0], id='V2', status='fail', result='Synthetic failed comparison'))
        self.write_table('validation', checks)
        result = audit_module.audit(self.project)
        self.assertFalse(result['ready'])
        self.assertTrue(result['integrity_ok'])
        self.assertEqual({r['id'] for r in result['status_findings']}, {'V2'})

    def test_failed_attempt_with_missing_output_still_fails_integrity(self):
        self.set_cell('runs', 'status', 'failed')
        (self.project / 'data/derived/result.csv').unlink()
        result = audit_module.audit(self.project)
        self.assertFalse(result['ready'])
        self.assertFalse(result['integrity_ok'])
        self.assertTrue(result['integrity_errors'])
        self.assertTrue(any(r['table'] == 'runs' for r in result['status_findings']))

    def test_invalid_status_is_an_integrity_error(self):
        self.set_cell('runs', 'status', 'probably_ok')
        result = audit_module.audit(self.project)
        self.assertFalse(result['ready'])
        self.assertFalse(result['integrity_ok'])
        self.assertTrue(any('invalid status' in e for e in result['integrity_errors']))

    def test_unverified_source_keeps_evidence_unready_despite_existing_files(self):
        self.set_cell('sources', 'status', 'pending', index=1)
        result = audit_module.audit(self.project)
        self.assertFalse(result['ready'])
        self.assertTrue(result['integrity_ok'])
        self.assertTrue(any(r['table'] == 'sources' and r['status'] == 'pending'
                            for r in result['status_findings']))

    def test_invalid_root_returns_both_kinds_without_traceback(self):
        result = audit_module.audit(self.directory / 'absent')
        self.assertFalse(result['ready'])
        self.assertFalse(result['integrity_ok'])
        self.assertTrue(result['integrity_errors'])
        self.assertEqual(result['status_findings'], [])


if __name__ == '__main__':
    unittest.main()
