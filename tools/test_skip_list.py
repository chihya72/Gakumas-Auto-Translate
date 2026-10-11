"""Verify skipped scripts stay excluded after pending files are cleaned up."""

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gakumas_auto_translate.modules import checker, config, octo_source, preprocessor, skip_list


class SkipListTests(unittest.TestCase):
    def setUp(self):
        with tempfile.NamedTemporaryFile(dir=Path(__file__).parent, suffix='.json', delete=False) as file:
            self.list_path = Path(file.name)
        self.addCleanup(self.list_path.unlink, missing_ok=True)
        self.addCleanup(self.list_path.with_suffix('.json.part').unlink, missing_ok=True)
        self.list_path.write_text('[]\n', encoding='utf-8')
        patcher = patch.object(skip_list, 'SKIP_LIST_FILE', self.list_path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_updates_persist_sorted_unique_filenames_and_allow_manual_removal(self):
        self.assertTrue(skip_list.add_untranslatable_file('adv_z.txt'))
        self.assertTrue(skip_list.add_untranslatable_file('adv_a.txt'))
        self.assertFalse(skip_list.add_untranslatable_file('adv_z.txt'))
        self.assertEqual(json.loads(self.list_path.read_text(encoding='utf-8')), ['adv_a.txt', 'adv_z.txt'])
        self.assertFalse(self.list_path.with_suffix('.json.part').exists())
        self.list_path.write_text('["adv_a.txt"]\n', encoding='utf-8')
        self.assertEqual(skip_list.load_untranslatable_files(), {'adv_a.txt'})

    def test_missing_list_starts_empty_and_can_be_created_by_preprocessing(self):
        self.list_path.unlink()
        self.assertEqual(skip_list.load_untranslatable_files(), set())
        self.assertTrue(skip_list.add_untranslatable_file('adv_empty.txt'))
        self.assertEqual(skip_list.load_untranslatable_files(), {'adv_empty.txt'})

    def test_invalid_list_reports_an_error_instead_of_disabling_exclusions(self):
        for value in ({'files': []}, [42], ['..\\other.txt']):
            self.list_path.write_text(json.dumps(value), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'JSON 数组'):
                skip_list.load_untranslatable_files()

    def download(self, names):
        skip_list.add_untranslatable_file('adv_empty.txt')
        client = MagicMock()
        client.manifest.return_value = {'version': 205100, 'resources': [{'name': name} for name in names]}
        client.download.return_value = ([Path('adv_new.txt')], [])
        with patch.object(octo_source, 'OctoClient', return_value=client), \
             patch.object(config, 'get_source_settings', return_value={}), \
             patch.object(config, 'remember_octo_version'), patch.object(Path, 'glob', return_value=[]), \
             patch.object(Path, 'mkdir'):
            result = checker.download_new_files()
        return result, client

    def test_cdn_skips_listed_filename_even_when_no_local_copy_exists(self):
        result, client = self.download(['adv_empty.txt', 'adv_empty_02.txt', 'adv_new.txt', 'musics.txt'])
        self.assertTrue(result)
        self.assertEqual(client.download.call_args.args[0], [{'name': 'adv_empty_02.txt'}, {'name': 'adv_new.txt'}])

    def test_only_excluded_resources_make_no_download_request(self):
        result, client = self.download(['adv_empty.txt'])
        self.assertFalse(result)
        client.download.assert_not_called()

    def test_local_source_also_excludes_listed_files(self):
        skip_list.add_untranslatable_file('adv_empty.txt')
        def files(directory):
            return ['adv_empty.txt', 'adv_new.txt'] if directory == 'local-source' else []
        with patch.object(config, 'get_source_mode', return_value='local'), \
             patch.object(checker, 'get_dump_txt_path', return_value='local-source'), \
             patch.object(checker.os.path, 'exists', return_value=True), \
             patch.object(checker.os, 'listdir', side_effect=files), patch.object(checker.os, 'makedirs'), \
             patch.object(checker.shutil, 'copy2') as copy:
            self.assertTrue(checker.check_new_files())
        self.assertEqual(len(copy.call_args_list), 1)
        self.assertEqual(Path(copy.call_args.args[0]).name, 'adv_new.txt')

    def test_preprocessing_records_no_content_but_not_encoding_failures(self):
        def read(file, mode='r', **kwargs):
            if str(file).endswith('adv_encoding.txt'):
                raise UnicodeDecodeError('utf-8', b'\xff', 0, 1, 'invalid test input')
            return io.StringIO('[timeline]\n')
        with patch.object(preprocessor.os, 'listdir', return_value=['adv_empty.txt', 'adv_encoding.txt']), \
             patch('builtins.open', side_effect=read), patch.object(Path, 'mkdir'), \
             patch.object(preprocessor, 'replace_names_in_csv'), patch.object(preprocessor, 'clean_html_in_csv_dict'):
            preprocessor.preprocess_txt_files()
        self.assertEqual(skip_list.load_untranslatable_files(), {'adv_empty.txt'})

    def test_preprocessing_translatable_dialogue_does_not_add_it_to_list(self):
        output = io.StringIO()
        class KeptBuffer(io.StringIO):
            def close(self):
                pass
        output = KeptBuffer()
        def open_csv(file, mode='r', **kwargs):
            return output if mode == 'w' else io.StringIO('[message text=こんにちは name=ことね]\n')
        with patch.object(preprocessor.os, 'listdir', return_value=['adv_dialogue.txt']), \
             patch('builtins.open', side_effect=open_csv), patch.object(Path, 'mkdir'), \
             patch.object(preprocessor.shutil, 'copy2'), patch.object(preprocessor, 'remove_r_tags_inplace'), \
             patch.object(preprocessor, 'replace_names_in_csv'), patch.object(preprocessor, 'clean_html_in_csv_dict'):
            preprocessor.preprocess_txt_files()
        self.assertIn('こんにちは', output.getvalue())
        self.assertEqual(skip_list.load_untranslatable_files(), set())


if __name__ == '__main__':
    unittest.main()
