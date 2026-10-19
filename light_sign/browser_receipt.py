"""通过 Streamlit 组件读取、保存当前浏览器的活动签到标记。"""

from pathlib import Path

import streamlit as st
import streamlit.components.v2 as components

_receipt_component = components.component(
    "lightsign_browser_receipt",
    html='<small role="status" aria-live="polite">正在读取本地签到状态…</small>',
    js=Path(__file__).with_suffix(".js").read_text(encoding="utf-8"),
)


def browser_receipt(event_id, confirmed=False):
    result = _receipt_component(
        data={"event": event_id, "confirmed": confirmed},
        default={"receipt": None},
        key="browser_checkin_receipt",
        on_receipt_change=lambda: None,
    )
    receipt = result.receipt
    # 活动切换时，旧活动的异步组件结果不能启用新活动按钮。
    if not isinstance(receipt, dict) or receipt.get("event") != event_id:
        return None
    return receipt
