"""ONLYOFFICE 插件桥接存储：内存必须有界、免鉴权入口不得因畸形输入崩溃。"""
import time
import unittest

from fastapi import HTTPException

from backend.app.onlyoffice_bridge_api import BridgeStore


class BridgeStoreTest(unittest.TestCase):
    def test_trace_only_channels_are_bounded(self) -> None:
        store = BridgeStore(max_channels=64, ttl=3600)
        for index in range(1000):
            store.record_trace(f"chan-{index}", {"stage": "x", "nonce": index, "type": "t"})
        self.assertLessEqual(len(store.traces), 64)
        self.assertLessEqual(len(store.last_seen), 64)
        self.assertEqual([], store.list_traces("never-seen"))

    def test_stale_channels_are_pruned_by_ttl(self) -> None:
        store = BridgeStore(max_channels=64, ttl=10)
        store.record_trace("old", {"stage": "x"})
        store.last_seen["old"] = time.time() - 100
        store.record_trace("fresh", {"stage": "x"})
        self.assertEqual([], store.list_traces("old"))
        self.assertNotIn("old", store.traces)

    def test_non_numeric_nonce_does_not_crash(self) -> None:
        store = BridgeStore()
        store.record_trace("c", {"stage": "s", "nonce": "not-a-number"})
        store.commands["c"] = {"nonce": "garbage", "type": "cmd"}
        self.assertIsNone(store.poll("c", 0))

    def test_overlong_channel_id_rejected(self) -> None:
        store = BridgeStore()
        with self.assertRaises(HTTPException):
            store.record_trace("x" * 500, {"stage": "s"})
        with self.assertRaises(HTTPException):
            store.poll("x" * 500)

    def test_submit_then_poll_delivers_command(self) -> None:
        store = BridgeStore()
        store.submit("c", {"nonce": 5, "action": "select", "fieldCode": "report_no"})
        delivered = store.poll("c", 0)
        self.assertEqual("select", delivered["action"])
        # after 达到已投递 nonce 后不再重复投递
        self.assertIsNone(store.poll("c", 5))

    def test_log_fields_are_sanitized(self) -> None:
        store = BridgeStore()
        store.record_trace("c", {"stage": "evil\nstage", "type": "a\nb", "nonce": 1})
        events = store.list_traces("c")
        self.assertEqual("evilstage", events[-1]["stage"])
        self.assertEqual("ab", events[-1]["type"])


if __name__ == "__main__":
    unittest.main()
