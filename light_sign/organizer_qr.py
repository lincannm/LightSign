"""组织者二维码的签发、有效期展示与定时刷新。"""

from contextlib import closing
from html import escape
import io
import os
from time import time
from urllib.parse import urlsplit

import qrcode
import streamlit as st

from light_sign import network, store
from light_sign.links import participant_link


def clear_qr():
    for name in ("token", "token_event", "token_expires", "participant_link", "qr_png"):
        st.session_state.pop(name, None)


def issue_qr(connection, key, event_id, ttl):
    base_url = network.participant_base_url(
        scheme=os.environ.get("LIGHTSIGN_PARTICIPANT_SCHEME", urlsplit(st.context.url).scheme or "https"),
        port=int(os.environ.get("LIGHTSIGN_PARTICIPANT_PORT", "8504")),
        host=os.environ.get("LIGHTSIGN_PARTICIPANT_HOST", "0.0.0.0"),
        override=os.environ.get("LIGHTSIGN_PARTICIPANT_URL"),
    )
    now = int(time())
    token = store.issue(connection, key, event_id, ttl, now=now)
    link = participant_link(base_url, token)
    buffer = io.BytesIO()
    qrcode.make(link).convert("RGB").save(buffer, format="PNG")
    st.session_state.update(
        token=token, token_event=event_id, token_expires=now + ttl,
        participant_link=link, qr_png=buffer.getvalue(),
    )


def show_unavailable_qr(message):
    st.html(
        '<div role="img" aria-label="' + escape(message, quote=True) + '" style="'
        'width:330px;max-width:100%;aspect-ratio:1;background:#000;color:#fff;'
        'display:flex;align-items:center;justify-content:center;border-radius:12px;'
        'font-size:24px;font-weight:600;text-align:center;">'
        + escape(message) + '</div>'
    )
    st.warning(message)


@st.fragment(run_every=1)
def show_qr(event_id, ttl, auto_refresh):
    if (st.session_state.get("token_event") != event_id
            or not st.session_state.get("token")
            or not st.session_state.get("participant_link")):
        return

    # 每次片段刷新独立打开并关闭连接，不能复用主页面已关闭的连接。
    with closing(store.connect()) as connection:
        key = store.key()
        now = int(time())
        payload, error = store.verify(connection, key, st.session_state.token, now=now)
        if error == "二维码已过期":
            # verify 优先检查过期；续签前还须确认旧凭证未撤销且活动仍开放。
            _, unavailable = store.verify(
                connection, key, st.session_state.token,
                now=st.session_state.get("token_expires", 0) - 1,
            )
            if unavailable:
                error = unavailable
            elif auto_refresh:
                try:
                    issue_qr(connection, key, event_id, ttl)
                    payload, error = store.verify(connection, key, st.session_state.token, now=now)
                except (ValueError, OSError) as exception:
                    st.error(f"二维码自动刷新失败：{exception}")

        if error:
            show_unavailable_qr(error)
            if error == "二维码已过期":
                st.caption('点击“生成限时二维码”重新生成，或开启“二维码自动刷新”。')
            return

    # 热更新前已生成的会话可能尚未缓存 PNG，按现有链接补建即可。
    if not st.session_state.get("qr_png"):
        buffer = io.BytesIO()
        qrcode.make(st.session_state.participant_link).convert("RGB").save(buffer, format="PNG")
        st.session_state.qr_png = buffer.getvalue()
    st.image(st.session_state.qr_png, width=330)
    st.caption(f"二维码有效期剩余 {max(0, payload['x'] - now)} 秒")
    st.download_button(
        "下载二维码 PNG", st.session_state.qr_png, "activity_qr.png", "image/png",
    )
    st.caption("手机连接同一 Wi-Fi，使用系统相机扫码即可签到。")
    st.caption("已开启自动刷新，到期后自动生成新二维码。" if auto_refresh else "自动刷新已关闭，到期后二维码将变黑。")
