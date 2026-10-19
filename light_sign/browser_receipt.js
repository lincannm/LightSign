const reported = new WeakMap();

export default function ({ parentElement, data, setStateValue }) {
  const event = data.event;
  const storageKey = `lightsign:checkin:v1:${event}`;
  const message = parentElement.querySelector('[role="status"]');

  function sync() {
    let checkedIn = false;
    let available = true;
    try {
      // 成功标记只包含活动编号，不保存参与代号、签名或个人信息。
      if (data.confirmed) localStorage.setItem(storageKey, "checked-in");
      checkedIn = localStorage.getItem(storageKey) === "checked-in";
      if (!checkedIn) {
        const probe = `${storageKey}:probe`;
        localStorage.setItem(probe, "1");
        localStorage.removeItem(probe);
      }
    } catch {
      available = false;
      checkedIn = Boolean(data.confirmed);
    }
    const receipt = { event, checkedIn, available };
    message.textContent = checkedIn
      ? "本浏览器已完成本活动签到。"
      : available ? "本浏览器可参加本活动签到。"
        : "无法使用浏览器本地存储，请允许保存网站数据后重试。";
    const serialized = JSON.stringify(receipt);
    if (reported.get(parentElement) !== serialized) {
      reported.set(parentElement, serialized);
      setStateValue("receipt", receipt);
    }
  }

  function onStorage(event) {
    if (event.key === storageKey || event.key === null) sync();
  }
  sync();
  window.addEventListener("storage", onStorage);
  return () => window.removeEventListener("storage", onStorage);
}
