import sys
import types
import unittest


doubao_stub = types.ModuleType('backend.models.doubao_api')


class _StubDoubaoError(Exception):
    pass


async def _stub_call_text_model(*args, **kwargs):
    raise AssertionError('call_text_model should not be used in filtering logic tests')


doubao_stub.DoubaoError = _StubDoubaoError
doubao_stub.call_text_model = _stub_call_text_model
sys.modules.setdefault('backend.models.doubao_api', doubao_stub)

filtering_tools_stub = types.ModuleType('backend.services.filtering_tools')
filtering_tools_stub.TOOL_DEFINITIONS = {}


async def _stub_tool(*args, **kwargs):
    raise AssertionError('filtering tools should not be used in filtering logic tests')


filtering_tools_stub.compute_blur_metrics = _stub_tool
filtering_tools_stub.compute_exposure_metrics = _stub_tool
filtering_tools_stub.compute_noise_metrics = _stub_tool
filtering_tools_stub.inspect_batch_images = _stub_tool
filtering_tools_stub.inspect_image = _stub_tool
filtering_tools_stub.list_batch_items = _stub_tool
sys.modules.setdefault('backend.services.filtering_tools', filtering_tools_stub)

from backend.services.filtering_agent import _normalize_filter_dsl
from backend.services.filtering_executor import execute_filter_dsl


class FilteringLogicTestCase(unittest.TestCase):
    def test_keep_highest_single_item_query_sets_limit_to_one(self) -> None:
        dsl = _normalize_filter_dsl(
            '保留质量最高的那张',
            {
                'mode': 'keep_matching',
                'logic': 'and',
                'rules': [
                    {'field': 'quality_fusion.final_score', 'op': '>=', 'value': 70},
                ],
            },
            domain_count=2,
        )

        self.assertEqual(dsl['limit'], 1)
        self.assertEqual(dsl['sort'], {'field': 'quality_fusion.final_score', 'direction': 'desc'})
        self.assertEqual(dsl['rules'], [])

    def test_execute_filter_keeps_only_top_item_for_single_item_query(self) -> None:
        items = [
            {
                'upload_id': 'high',
                'filename': 'high.jpg',
                'quality_fusion': {'final_score': 88.0},
                'snapshot': {},
            },
            {
                'upload_id': 'low',
                'filename': 'low.jpg',
                'quality_fusion': {'final_score': 57.0},
                'snapshot': {},
            },
        ]
        dsl = _normalize_filter_dsl(
            '保留质量最高的那张',
            {
                'mode': 'keep_matching',
                'logic': 'and',
                'rules': [],
            },
            domain_count=len(items),
        )

        result = execute_filter_dsl(items, dsl)

        self.assertEqual(result['summary'], {'total': 2, 'kept': 1, 'removed': 1})
        self.assertEqual([item['upload_id'] for item in result['kept']], ['high'])
        self.assertEqual([item['upload_id'] for item in result['removed']], ['low'])
        self.assertEqual(result['removed'][0]['reason'], '超过保留数量上限')

    def test_execute_filter_matches_content_search_text(self) -> None:
        items = [
            {
                'upload_id': 'portrait',
                'filename': 'portrait.jpg',
                'quality_fusion': {'final_score': 82.0},
                'content': {
                    'caption': '一名人物站在建筑前',
                    'objects': [{'label': 'person'}, {'label': 'building'}],
                },
                'semantic': {'semantic_tags': ['人物', '城市']},
                'snapshot': {},
            },
            {
                'upload_id': 'landscape',
                'filename': 'landscape.jpg',
                'quality_fusion': {'final_score': 80.0},
                'content': {'caption': '草地和天空', 'objects': [{'label': 'grass'}]},
                'semantic': {'semantic_tags': ['自然']},
                'snapshot': {},
            },
        ]

        result = execute_filter_dsl(
            items,
            {
                'mode': 'keep_matching',
                'logic': 'and',
                'rules': [{'field': 'content.search_text', 'op': 'contains', 'value': '人物'}],
                'sort': {'field': 'quality_fusion.final_score', 'direction': 'desc'},
            },
        )

        self.assertEqual(result['summary'], {'total': 2, 'kept': 1, 'removed': 1})
        self.assertEqual(result['kept'][0]['upload_id'], 'portrait')
        self.assertIn('图像内容 contains 人物', result['kept'][0]['reason'])
        self.assertTrue(result['kept'][0]['decision_basis'])

    def test_fallback_plan_can_remove_content_matches(self) -> None:
        dsl = _normalize_filter_dsl(
            '去掉包含人物的图片',
            {
                'mode': 'remove_matching',
                'logic': 'and',
                'rules': [{'field': 'content.search_text', 'op': 'contains', 'value': '人物'}],
            },
            domain_count=2,
        )

        self.assertEqual(dsl['mode'], 'remove_matching')
        self.assertEqual(dsl['rules'][0]['field'], 'content.search_text')


if __name__ == '__main__':
    unittest.main()
