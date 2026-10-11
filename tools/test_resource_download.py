"""Offline checks for Octo compatibility, missing-file recovery and menus."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gakumas_auto_translate.modules import checker, config, octo_source


def response(status=200, content=b""):
    result = MagicMock(status_code=status, content=content)
    result.__enter__.return_value = result
    if status >= 400:
        result.raise_for_status.side_effect = RuntimeError(f"HTTP {status}")
    return result


def fixture_manifest():
    # Wire numbers from HatsuboshiToolkit/proto/octodb.proto, independently
    # encoded so using the wrong field number in the reader fails this check.
    def string(number, text):
        value = text.encode()
        return bytes([number * 8 + 2, len(value)]) + value
    resource = string(3, "adv_new.txt") + b"\x20\x03\x48\x03" + string(11, "object")
    deleted = string(3, "adv_deleted.txt") + b"\x48\x04"
    return (b"\x08\x07\x22" + bytes([len(resource)]) + resource + b"\x22" + bytes([len(deleted)]) + deleted
            + string(5, "https://example.test/{o}"))


class DownloadTests(unittest.TestCase):
    def client(self, probes=0):
        client = octo_source.OctoClient({"octo_version": 205100, "octo_version_probes": probes, "download_workers": 2})
        client.http = MagicMock()
        return client

    def test_encrypted_manifest_reads_wire_fields_and_ignores_deleted_resources(self):
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import pad
        iv = b"0" * 16
        encrypted = iv + AES.new(hashlib.sha256(octo_source.MANIFEST_KEY.encode()).digest(), AES.MODE_CBC, iv).encrypt(pad(fixture_manifest(), 16))
        result = octo_source.decode_manifest(encrypted)
        self.assertEqual(result, {"revision": 7, "url_format": "https://example.test/{o}",
                                 "resources": [{"name": "adv_new.txt", "size": 3, "object_name": "object"}]})

    def test_version_probe_skips_400_but_keeps_a_newer_available_version(self):
        client = self.client(probes=2)
        client.http.get.side_effect = [response(400), response(200), response(404), response(200, b"manifest")]
        with patch.object(octo_source, "decode_manifest", return_value={"revision": 7, "resources": []}):
            result = client.manifest()
        self.assertEqual(result['version'], 205200)
        self.assertTrue(client.http.get.call_args_list[-1].args[0].endswith('/205200/list/0'))

    def test_network_and_server_failures_do_not_report_no_updates(self):
        client = self.client(probes=1)
        client.http.get.return_value = response(503)
        with self.assertRaisesRegex(RuntimeError, '503'):
            client.manifest()
        self.assertEqual(client.http.get.call_count, 1)

    def test_atomic_download_reuses_original_and_rejects_truncated_data(self):
        client = self.client()
        with tempfile.NamedTemporaryFile(dir=Path(__file__).parent, prefix='adv_resource_test_', suffix='.txt', delete=False) as file:
            target = Path(file.name)
        temporary = target.with_suffix('.txt.part')
        try:
            target.unlink()
            item = {"name": target.name, "size": 4, "object_name": "text"}
            client.http.get.return_value = response(200, b"half"[:2])
            with self.assertRaisesRegex(ValueError, '不完整'):
                client.download_one(item, 'https://example.test/{o}', target.parent)
            self.assertFalse(target.exists())
            client.http.get.return_value = response(200, b"text")
            self.assertEqual(client.download_one(item, 'https://example.test/{o}', target.parent), target)
            self.assertEqual(target.read_bytes(), b'text')
            requests = client.http.get.call_count
            client.download_one(item, 'https://example.test/{o}', target.parent)
            self.assertEqual(client.http.get.call_count, requests)
            self.assertFalse(temporary.exists())
        finally:
            target.unlink(missing_ok=True)
            temporary.unlink(missing_ok=True)

    def test_partial_failure_retains_successful_paths(self):
        client = self.client()
        items = [{'name': 'adv_ok.txt'}, {'name': 'adv_failed.txt'}]
        def download(item, *_):
            if item['name'] == 'adv_failed.txt':
                raise RuntimeError('connection interrupted')
            return Path('adv_ok.txt')
        with patch.object(client, 'download_one', side_effect=download):
            paths, failures = client.download(items, {'url_format': 'unused'}, Path(__file__).parent)
        self.assertEqual(paths, [Path('adv_ok.txt')])
        self.assertEqual(failures, ['adv_failed.txt'])

    def test_bad_acb_and_escaping_filename_are_rejected_before_writing(self):
        client = self.client()
        client.http.get.return_value = response(200, b'not an ACB')
        with patch.object(Path, 'is_file', return_value=False), patch.object(Path, 'write_bytes') as write:
            with self.assertRaisesRegex(ValueError, '不是 ACB'):
                client.download_one({'name': 'sud_vo_amao_home_test.acb', 'object_name': 'audio'}, 'https://example.test/{o}', Path(__file__).parent)
            with self.assertRaisesRegex(ValueError, 'filename'):
                client.download_one({'name': '../escape.acb', 'object_name': 'audio'}, 'https://example.test/{o}', Path(__file__).parent)
        write.assert_not_called()

    def test_story_ingest_skips_finished_and_existing_pending_texts(self):
        client = MagicMock()
        client.manifest.return_value = {'version': 205100, 'resources': [
            {'name': name} for name in ['adv_done.txt', 'adv_draft.txt', 'adv_new.txt', 'musics.txt', 'other.acb']]}
        client.download.return_value = ([Path('adv_new.txt')], [])
        def files(path, _pattern):
            return [Path('adv_done.txt')] if path.name == 'data' else [Path('adv_draft.txt')]
        with patch.object(octo_source, 'OctoClient', return_value=client), patch.object(config, 'get_source_settings', return_value={}), \
             patch.object(config, 'remember_octo_version'), patch.object(Path, 'glob', files), patch.object(Path, 'mkdir'):
            self.assertTrue(checker.download_new_files())
        self.assertEqual(client.download.call_args.args[0], [{'name': 'adv_new.txt'}])

    def test_config_save_preserves_download_settings_and_translation_mode(self):
        with tempfile.NamedTemporaryFile(dir=Path(__file__).parent, suffix='.json', delete=False) as file:
            target = Path(file.name)
        try:
            target.write_text(json.dumps({'octo_version': 205300, 'download_workers': 3, 'extra': 'keep'}), encoding='utf-8')
            with patch.object(config, 'CONFIG_FILE', str(target)), patch.object(config, 'translation_mode', 'chinese'), \
                 patch.object(config, 'source_mode', 'octo'), patch.object(config, 'dump_txt_path', None):
                self.assertTrue(config.save_config())
            data = json.loads(target.read_text(encoding='utf-8'))
            self.assertEqual(data['octo_version'], 205300)
            self.assertEqual(data['download_workers'], 3)
            self.assertEqual(data['translation_mode'], 'chinese')
            self.assertEqual(data['extra'], 'keep')
        finally:
            target.unlink(missing_ok=True)


if __name__ == '__main__':
    unittest.main()
