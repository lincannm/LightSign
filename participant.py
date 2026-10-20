"""参与者专用入口：不包含活动管理、人数清点或签到记录页面。"""

import cv2
import numpy as np
import streamlit as st
from PIL import Image, UnidentifiedImageError

from light_sign import store
from light_sign.browser_receipt import browser_receipt
from light_sign.links import extract_token


def is_mobile():
    user_agent = st.context.headers.get("User-Agent", "").lower()
    return any(device in user_agent for device in ("mobile", "android", "iphone", "ipad", "ipod"))


def decode_image(file):
    try:
        qr_image = np.array(Image.open(file).convert("RGB"))
        decoded, _, _ = cv2.QRCodeDetector().detectAndDecode(qr_image)
        if decoded:
            st.success("扫码成功")
            return extract_token(decoded)
        st.warning("未能识别二维码，请重新拍摄或改用手动输入")
    except (UnidentifiedImageError, ValueError, OSError, cv2.error):
        st.error("无法读取二维码图片")
    return ""


def main():
    st.set_page_config(page_title="轻签 · 参与者签到", page_icon="🔷", layout="centered")
    st.title("轻签 · 参与者签到")
    st.caption("自愿参加 / 无需实名 / 同一浏览器同一活动只签一次")
    st.info("只需填写活动内使用的参与代号，不收集姓名、学号或人脸信息。")

    token = extract_token(st.query_params.get("token", ""))
    if token:
        st.caption("已从活动链接载入二维码凭证")
        if st.button("改用其他活动二维码"):
            st.query_params.clear()
            st.rerun()
    else:
        method = st.radio("二维码输入方式", ["手动输入文本", "上传图片", "摄像头扫码"],
                          index=2 if is_mobile() else 0, horizontal=True)
        if method == "手动输入文本":
            token = extract_token(st.text_area("二维码文本或活动签到链接", height=100))
        elif method == "上传图片":
            file = st.file_uploader("上传二维码图片", type=["png", "jpg", "jpeg"])
            if file:
                token = decode_image(file)
        else:
            file = st.camera_input("使用摄像头扫描二维码")
            if file:
                token = decode_image(file)

    connection = store.connect()
    try:
        key = store.key()
        payload, error = store.verify(connection, key, token) if token else (None, None)
        event_id = payload["e"] if payload else None
        if error:
            st.warning(error)
        elif not token:
            st.caption("请先扫描二维码或输入活动签到链接。")

        confirmed_events = st.session_state.get("confirmed_events", set())
        confirmed = event_id in confirmed_events
        receipt = None
        if event_id:
            event = connection.execute("SELECT title FROM events WHERE id=?", (event_id,)).fetchone()
            st.subheader(event["title"])
            receipt = browser_receipt(event_id, confirmed)

        checked_in = confirmed or bool(receipt and receipt.get("checkedIn"))
        ready = bool(event_id and receipt and receipt.get("available"))
        if checked_in:
            st.success("本活动已签到，无需重复提交。")
        elif event_id and receipt is None:
            st.caption("正在确认浏览器本地签到状态…")
        elif receipt and not receipt.get("available"):
            st.error("本地存储不可用。请允许此网站保存数据后刷新，再提交签到。")

        code = st.text_input("参与代号（请勿使用姓名或学号）", max_chars=24, disabled=checked_in)
        consent = st.checkbox("我自愿参加活动", disabled=checked_in)
        if st.button("本活动已签到" if checked_in else "提交签到", type="primary",
                     disabled=not ready or checked_in or not consent or not code.strip()):
            result = store.checkin(connection, key, token, code, consent)
            st.session_state.last_checkin = result
            if result["ok"] or result["reason"] == "本活动已签到":
                st.session_state.confirmed_events = confirmed_events | {result["event"]}
                st.rerun()
            st.warning(result["reason"])

    finally:
        connection.close()


if __name__ == "__main__":
    main()
