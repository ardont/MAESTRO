import unittest
from rag.answer_assets import format_answer_assets


class AnswerAssetsTests(unittest.TestCase):
    def test_all_sources_and_images_survive_in_final_text(self):
        text = format_answer_assets({'answer': 'Ответ [Первый](https://example.com/one)',
            'citations': [{'title': 'Первый', 'url': 'https://example.com/one'},
                          {'title': 'Второй', 'url': 'https://example.com/two'}],
            'images': ['https://example.com/image.png', 'https://example.com/image.png', 'javascript:bad']})
        self.assertEqual(text.count('https://example.com/one'), 1)
        self.assertIn('[Второй](https://example.com/two)', text)
        self.assertEqual(text.count('https://example.com/image.png'), 1)
        self.assertNotIn('javascript:', text)

    def test_local_image_uses_public_media_service(self):
        text = format_answer_assets({'answer':'Ответ', 'images':['media/kb_images/test.png', '../secret']})
        self.assertIn('http://localhost:8989/media/kb_images/test.png', text)
        self.assertNotIn('secret', text)
