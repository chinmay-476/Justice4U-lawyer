import unittest
from unittest.mock import patch

from core import app
import routes.public_routes  # noqa: F401
import routes.auth_routes as auth_routes
import routes.admin_routes as admin_routes


class MasterAuthAndDevDocsTests(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['ENABLE_DEV_DOCS'] = True
        self.client = app.test_client()

    def _set_admin_session(self):
        with self.client.session_transaction() as sess:
            sess['is_admin'] = True

    def test_master_admin_login_success(self):
        audit_events = []
        with patch.object(auth_routes, 'verify_master_credentials', return_value=True), patch.object(
            auth_routes,
            'log_login_audit',
            side_effect=lambda **kwargs: audit_events.append(kwargs),
        ):
            response = self.client.post(
                '/admin/login',
                data={'email': 'chinmaysahoo63715@gmail.com', 'password': 'chin1987'},
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin', response.headers.get('Location', ''))
        with self.client.session_transaction() as sess:
            self.assertTrue(sess.get('is_admin'))
            self.assertTrue(sess.get('is_master_admin'))
        self.assertEqual(audit_events[-1]['status'], 'success')
        self.assertEqual(audit_events[-1]['source'], 'master')

    def test_master_admin_login_failure(self):
        audit_events = []
        with patch.object(auth_routes, 'verify_master_credentials', return_value=False), patch.object(
            auth_routes,
            'log_login_audit',
            side_effect=lambda **kwargs: audit_events.append(kwargs),
        ):
            response = self.client.post(
                '/admin/login',
                data={'email': 'chinmaysahoo63715@gmail.com', 'password': 'wrong'},
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 200)
        with self.client.session_transaction() as sess:
            self.assertFalse(bool(sess.get('is_admin')))
        self.assertEqual(audit_events[-1]['status'], 'failure')

    def test_master_user_login_success(self):
        audit_events = []
        with patch.object(auth_routes, '_get_user_by_email', return_value=None), patch.object(
            auth_routes, 'verify_master_credentials', return_value=True
        ), patch.object(auth_routes, 'log_login_audit', side_effect=lambda **kwargs: audit_events.append(kwargs)):
            response = self.client.post(
                '/login',
                data={'email': 'chinmaysahoo63715@gmail.com', 'password': 'chin1987'},
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 302)
        self.assertIn('/user/home', response.headers.get('Location', ''))
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get('user_id'), -1)
            self.assertTrue(sess.get('is_master_user'))
        self.assertEqual(audit_events[-1]['status'], 'success')
        self.assertEqual(audit_events[-1]['source'], 'master')

    def test_master_user_login_failure(self):
        audit_events = []
        with patch.object(auth_routes, '_get_user_by_email', return_value=None), patch.object(
            auth_routes, 'verify_master_credentials', return_value=False
        ), patch.object(auth_routes, 'log_login_audit', side_effect=lambda **kwargs: audit_events.append(kwargs)):
            response = self.client.post(
                '/login',
                data={'email': 'chinmaysahoo63715@gmail.com', 'password': 'wrong'},
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Invalid credentials', response.data)
        self.assertEqual(audit_events[-1]['status'], 'failure')

    def test_dev_guide_auth_and_gate(self):
        unauth = self.client.get('/admin/dev-guide', follow_redirects=False)
        self.assertEqual(unauth.status_code, 302)
        self.assertIn('/admin/login', unauth.headers.get('Location', ''))

        self._set_admin_session()
        app.config['ENABLE_DEV_DOCS'] = False
        disabled = self.client.get('/admin/dev-guide')
        self.assertEqual(disabled.status_code, 404)

        app.config['ENABLE_DEV_DOCS'] = True
        with patch.object(admin_routes, 'get_db_connection', return_value=None):
            enabled = self.client.get('/admin/dev-guide')
        self.assertEqual(enabled.status_code, 200)
        self.assertIn(b'Developer Guide', enabled.data)

    def test_login_audit_api_returns_payload(self):
        self._set_admin_session()
        mock_payload = {
            'items': [
                {
                    'id': 1,
                    'email_or_identity': 'chinmaysahoo63715@gmail.com',
                    'role_attempted': 'admin',
                    'status': 'success',
                    'source': 'master',
                    'ip_address': '127.0.0.1',
                    'user_agent': 'pytest',
                    'created_at': '2026-02-23 00:00:00',
                }
            ],
            'total': 1,
            'page': 1,
            'per_page': 25,
            'sort': 'desc',
        }
        with patch.object(admin_routes, 'get_login_audit_entries', return_value=mock_payload):
            response = self.client.get('/admin/api/login-audit?page=1&per_page=25&sort=desc')

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['total'], 1)
        self.assertEqual(len(data['items']), 1)


if __name__ == '__main__':
    unittest.main()
