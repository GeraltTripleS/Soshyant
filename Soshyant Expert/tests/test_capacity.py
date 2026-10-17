import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from expert.capacity import CapacityPlanner


class CapacityTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.planner = CapacityPlanner(SimpleNamespace(root=root, settings={
            'model_file': str(root / 'assets/model.gguf'), 'queue_size': 8}))

    def test_attention_memory_formula(self):
        result = self.planner.estimate({'model_id':'qwen3-8b'})
        self.assertEqual(result['kv_gib_per_sequence'], 1.125)
        hybrid = self.planner.estimate({})
        self.assertEqual(hybrid['kv_gib_per_sequence'], .5)
        self.assertEqual(hybrid['recurrent_gib_per_sequence'], .2)

    def test_users_and_context_increase_memory_requirement(self):
        base = self.planner.estimate({'model_id':'qwen3-8b','users':10})
        busy = self.planner.estimate({'model_id':'qwen3-8b','users':100})
        long = self.planner.estimate({'model_id':'qwen3-8b','users':100,'context_tokens':32768})
        self.assertGreater(busy['memory_gpu_count'], base['memory_gpu_count'])
        self.assertGreater(long['memory_gpu_count'], busy['memory_gpu_count'])
        self.assertFalse(base['speed_guaranteed'])
        self.assertIsNone(base['throughput_gpu_count'])

    def test_activity_rounds_up_and_quantization_changes_weights(self):
        result = self.planner.estimate({'users':11,'activity_percent':10})
        self.assertEqual(result['active_generations'], 2)
        q4 = self.planner.estimate({'model_id':'qwen3-8b'})
        q8 = self.planner.estimate({'model_id':'qwen3-8b','quantization':'Q8_0'})
        self.assertGreater(q8['weights_gib'], q4['weights_gib'])

    def test_small_cards_cannot_pool_memory(self):
        result = self.planner.estimate({'model_id':'qwen3-32b','gpu_gib':8,'users':100})
        self.assertIsNone(result['planned_gpu_count'])
        self.assertIsNone(result['ram_gib'])
        self.assertGreater(result['minimum_single_gpu_class_gib'], 8)

    def test_benchmark_is_not_transferred_to_comparison(self):
        result = self.planner.estimate({'users':100,'benchmark_tps':10})
        self.assertEqual(result['throughput_gpu_count'], 120)
        self.assertEqual(result['planned_gpu_count'], 120)
        for row in result['comparison']:
            self.assertEqual(row['memory_gpu_count'], row['planned_gpu_count'])
        self.assertGreater(result['ram_gib'], result['ram_floor_gib'])

    def test_invalid_requests(self):
        for data in [{'users':True},{'users':1.5},{'users':0},{'users':float('nan')},
                     {'model_id':[]},{'quantization':{}},{'model_id':'missing'},
                     {'context_tokens':999999},{'answer_tokens':2048,'context_tokens':2048},
                     {'benchmark_tps':True},{'benchmark_tps':float('inf')}, {'gpu_gib':-1}]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.planner.estimate(data)
