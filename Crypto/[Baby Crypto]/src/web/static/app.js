
(function () {
  "use strict";

  const out    = document.getElementById("out");
  const caret  = document.getElementById("caret");
  const phos   = document.getElementById("phosphor");
  const power  = document.getElementById("power");
  const sink   = document.getElementById("sink");
  const screen = document.getElementById("screen");
  const ledNet = document.getElementById("ledNet");
  const ledHdd = document.getElementById("ledHdd");
  const statusText = document.getElementById("statusText");
  const clockEl = document.getElementById("clock");

  let committed = "";
  let queue     = "";
  let inputBuf  = "";       // текущая набираемая строка (мгновенное эхо)
  let pendingEnter = false; // Enter нажат во время печати -> отправить по её концу
  let typer = null;         // таймер телетайпа
  const drainCbs = [];      // одноразовые колбэки «когда допечатано»

  let ws = null;
  let connected = false;

  const TICK_MS = 15;            // база кадра (плюс лёгкий джиттер 12–18)
  const MAX_BURST_MS = 2000;     // потолок на текущую порцию
  function tickDelay() { return 12 + Math.random() * 6; }

  const typing = () => queue.length > 0;

  function render() {
    out.textContent = typing() ? committed : committed + inputBuf;
    phos.scrollTop = phos.scrollHeight;
  }

  function pump() {
    if (queue.length === 0) {
      typer = null;
      render();
      while (drainCbs.length) { try { drainCbs.shift()(); } catch (e) {} }
      if (pendingEnter) { pendingEnter = false; sendLine(); }
      return;
    }
    const maxTicks = MAX_BURST_MS / TICK_MS;
    const step = Math.max(1, Math.ceil(queue.length / maxTicks));
    committed += queue.slice(0, step);
    queue = queue.slice(step);
    render();
    typer = setTimeout(pump, tickDelay());
  }

  function enqueue(text) {
    queue += text;
    if (!typer) typer = setTimeout(pump, 0);
  }

  function onDrain(cb) {
    if (!typing()) cb(); else drainCbs.push(cb);
  }

  function blip(el) {
    el.classList.add("on");
    clearTimeout(el._t);
    el._t = setTimeout(() => el.classList.remove("on"), 90);
  }

  function setStatus(txt, netOn) {
    statusText.textContent = txt;
    if (netOn === true)  ledNet.classList.add("on");
    if (netOn === false) ledNet.classList.remove("on");
  }

  setInterval(() => {
    const d = new Date(), p = (n) => String(n).padStart(2, "0");
    clockEl.textContent = p(d.getHours()) + ":" + p(d.getMinutes()) + ":" + p(d.getSeconds());
  }, 1000);

  const bootText = [
    "ОБЪЕКТ №17 · УЗЕЛ КРИПТОГРАФИЧЕСКОЙ СВЯЗИ",
    "",
    "[ПЗУ]  проверка контрольной суммы .......... ОК",
    "[ОЗУ]  тест ячеек 000000-00FFFF ............ ОК",
    "[КРИПТОМОДУЛЬ ВОЛХВ-3] инициализация ....... ОК",
    "[ПИТАНИЕ] стабилизация +5В/+12В ............ ОК",
    "",
    "установление связи с узлом…",
    ""
  ].join("\n") + "\n";

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    setStatus("УСТАНОВЛЕНИЕ КАНАЛА…", false);
    try {
      ws = new WebSocket(proto + "://" + location.host + "/ws");
    } catch (e) {
      setStatus("ОШИБКА КАНАЛА", false);
      enqueue("\n[СВЯЗЬ] не удалось открыть линию.\n");
      return;
    }
    ws.onopen = () => { connected = true; setStatus("КАНАЛ: УСТАНОВЛЕН", true); };
    ws.onmessage = (ev) => { blip(ledHdd); enqueue(ev.data); };
    ws.onclose = () => {
      connected = false; setStatus("КАНАЛ РАЗОРВАН", false);
      enqueue("\n[СВЯЗЬ] линия закрыта.\n");
    };
    ws.onerror = () => { setStatus("СБОЙ КАНАЛА", false); };
  }

  function sendLine() {
    if (!connected || !ws) return;
    ws.send(inputBuf + "\n");          // сервер читает построчно (readline)
    committed += inputBuf + "\n";      // эхо уже видно игроку -> фиксируем сразу
    inputBuf = "";
    render();
  }

  function focusSink() { try { sink.focus({ preventScroll: true }); } catch (e) {} }
  screen.addEventListener("mousedown", (e) => { e.preventDefault(); focusSink(); });

  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;   // не мешаем copy/paste
    if (e.key === "Enter") {
      e.preventDefault();
      if (typing()) pendingEnter = true;   // допечатается -> отправим
      else sendLine();
    } else if (e.key === "Backspace") {
      e.preventDefault();
      inputBuf = inputBuf.slice(0, -1);
      if (!typing()) render();
    } else if (e.key.length === 1) {
      e.preventDefault();
      inputBuf += e.key;
      if (!typing()) render();
    }
    focusSink();
  });

  sink.addEventListener("input", () => {
    if (sink.value) {
      inputBuf += sink.value;
      sink.value = "";
      if (!typing()) render();
    }
  });

  document.addEventListener("paste", (e) => {
    const t = (e.clipboardData || window.clipboardData).getData("text");
    if (t) {
      inputBuf += t.replace(/\r?\n/g, "");
      if (!typing()) render();
      e.preventDefault();
    }
  });

  window.addEventListener("load", () => {
    focusSink();
    setTimeout(() => {
      power.classList.add("off");
      enqueue(bootText);
      onDrain(connect);
    }, 900);
  });
})();
