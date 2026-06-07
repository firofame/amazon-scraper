import asyncio
import random
import json
import urllib.request
import websockets
import base64
from contextlib import asynccontextmanager

class CDPRequestResponse:
    def __init__(self, status, body_b64):
        self.status = status
        self.body_b64 = body_b64

    async def body(self):
        return base64.b64decode(self.body_b64)

class CDPRequest:
    def __init__(self, page):
        self.page = page

    async def get(self, url):
        res = await self.page.evaluate_js(
            f"""
            (async () => {{
                try {{
                    const resp = await fetch({json.dumps(url)});
                    const blob = await resp.blob();
                    return await new Promise((resolve, reject) => {{
                        const reader = new FileReader();
                        reader.onloadend = () => {{
                            const base64data = reader.result.split(',')[1];
                            resolve({{ status: resp.status, body: base64data }});
                        }};
                        reader.onerror = reject;
                        reader.readAsDataURL(blob);
                    }});
                }} catch (e) {{
                    return {{ status: 500, body: "" }};
                }}
            }})()
            """
        )
        return CDPRequestResponse(res["status"], res["body"])

class CDPMouse:
    def __init__(self, page):
        self.page = page

    async def move(self, x, y, steps=1):
        for i in range(1, steps + 1):
            await self.page.send("Input.dispatchMouseEvent", {
                "type": "mouseMoved",
                "x": int(x),
                "y": int(y)
            })
            await asyncio.sleep(0.02)

class CDPLocator:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector

    async def count(self):
        return await self.page.evaluate(f"document.querySelectorAll({json.dumps(self.selector)}).length")

    def nth(self, i):
        return CDPElement(self.page, self.selector, index=i)

class CDPElement:
    def __init__(self, page, selector=None, index=0, element_id=None):
        self.page = page
        self.selector = selector
        self.index = index
        self.element_id = element_id

    async def _resolve_id(self):
        if self.element_id is not None:
            return self.element_id
        self.element_id = await self.page.evaluate_js(
            f"""
            (() => {{
                const els = document.querySelectorAll({json.dumps(self.selector)});
                const el = els[{self.index}];
                if (!el) return null;
                window._cdp_elements = window._cdp_elements || {{}};
                window._cdp_element_counter = window._cdp_element_counter || 0;
                const newId = ++window._cdp_element_counter;
                window._cdp_elements[newId] = el;
                return newId;
            }})()
            """
        )
        return self.element_id

    async def get_attribute(self, name):
        el_id = await self._resolve_id()
        if el_id is None:
            return None
        return await self.page.evaluate_js(
            f"window._cdp_elements[{el_id}].getAttribute({json.dumps(name)})"
        )

    async def inner_text(self):
        el_id = await self._resolve_id()
        if el_id is None:
            return ""
        return await self.page.evaluate_js(
            f"window._cdp_elements[{el_id}].innerText"
        )

    async def query_selector(self, selector):
        el_id = await self._resolve_id()
        if el_id is None:
            return None
        sub_id = await self.page.evaluate_js(
            f"""
            (() => {{
                const parent = window._cdp_elements[{el_id}];
                if (!parent) return null;
                const el = parent.querySelector({json.dumps(selector)});
                if (!el) return null;
                window._cdp_elements = window._cdp_elements || {{}};
                window._cdp_element_counter = window._cdp_element_counter || 0;
                const newId = ++window._cdp_element_counter;
                window._cdp_elements[newId] = el;
                return newId;
            }})()
            """
        )
        if sub_id is None:
            return None
        return CDPElement(self.page, element_id=sub_id)

    async def click(self, timeout=None):
        el_id = await self._resolve_id()
        if el_id is None:
            return
        await self.page.evaluate_js(
            f"window._cdp_elements[{el_id}].click()"
        )

    async def evaluate(self, js_func_str):
        el_id = await self._resolve_id()
        if el_id is None:
            return None
        return await self.page.evaluate_js(
            f"({js_func_str})(window._cdp_elements[{el_id}])"
        )

    async def scroll_into_view_if_needed(self, timeout=None):
        el_id = await self._resolve_id()
        if el_id is None:
            return
        await self.page.evaluate_js(
            f"window._cdp_elements[{el_id}].scrollIntoView({{behavior: 'smooth', block: 'center'}})"
        )

    async def bounding_box(self):
        el_id = await self._resolve_id()
        if el_id is None:
            return None
        rect = await self.page.evaluate_js(
            f"""
            (() => {{
                const el = window._cdp_elements[{el_id}];
                if (!el) return null;
                const r = el.getBoundingClientRect();
                return {{ x: r.x + window.scrollX, y: r.y + window.scrollY, width: r.width, height: r.height }};
            }})()
            """
        )
        return rect

class CDPPage:
    def __init__(self, ws_url, tab_id, context):
        self.ws_url = ws_url
        self.tab_id = tab_id
        self.context = context
        self.ws = None
        self.id_counter = 0
        self.responses = {}
        self.read_task = None
        self.mouse = CDPMouse(self)
        self.request = CDPRequest(self)

    async def connect(self):
        self.ws = await websockets.connect(self.ws_url, max_size=None)
        self.read_task = asyncio.create_task(self._reader())
        await self.send("Page.enable")

    async def _reader(self):
        try:
            async for message in self.ws:
                data = json.loads(message)
                if "id" in data:
                    req_id = data["id"]
                    fut = self.responses.get(req_id)
                    if fut and not fut.done():
                        fut.set_result(data)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"CDP reader error: {e}")

    async def send(self, method, params=None):
        self.id_counter += 1
        req_id = self.id_counter
        payload = {
            "id": req_id,
            "method": method,
            "params": params or {}
        }
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self.responses[req_id] = fut
        await self.ws.send(json.dumps(payload))
        res = await fut
        del self.responses[req_id]
        if "error" in res:
            raise RuntimeError(f"CDP Error: {res['error']}")
        return res.get("result", {})

    async def goto(self, url, wait_until=None, timeout=None):
        await self.send("Page.navigate", {"url": url})
        for _ in range(120):
            try:
                state = await self.evaluate_js("document.readyState")
                if state == "complete":
                    break
            except Exception:
                pass
            await asyncio.sleep(0.5)

    async def evaluate_js(self, expression):
        res = await self.send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True
        })
        exception_details = res.get("exceptionDetails")
        if exception_details:
            raise RuntimeError(f"JS Error: {exception_details}")
        return res.get("result", {}).get("value")

    async def evaluate(self, expression, *args):
        expr_str = expression.strip()
        is_func = (
            expr_str.startswith("(") or
            expr_str.startswith("function") or
            "=>" in expr_str.split("\n")[0]
        )
        if is_func:
            json_args = [json.dumps(a) for a in args]
            expression = f"({expr_str})({', '.join(json_args)})"
        return await self.evaluate_js(expression)

    async def wait_for_selector(self, selector, timeout=15000):
        start_time = asyncio.get_event_loop().time()
        limit = timeout / 1000.0 if timeout else 15.0
        while True:
            exists = await self.evaluate_js(f"document.querySelector({json.dumps(selector)}) !== null")
            if exists:
                return
            if asyncio.get_event_loop().time() - start_time > limit:
                raise TimeoutError(f"Timeout waiting for selector: {selector}")
            await asyncio.sleep(0.2)

    async def query_selector_all(self, selector):
        ids = await self.evaluate_js(
            f"""
            (() => {{
                const els = Array.from(document.querySelectorAll({json.dumps(selector)}));
                window._cdp_elements = window._cdp_elements || {{}};
                window._cdp_element_counter = window._cdp_element_counter || 0;
                return els.map(el => {{
                    const newId = ++window._cdp_element_counter;
                    window._cdp_elements[newId] = el;
                    return newId;
                }});
            }})()
            """
        )
        return [CDPElement(self, element_id=eid) for eid in ids]

    async def query_selector(self, selector):
        eid = await self.evaluate_js(
            f"""
            (() => {{
                const el = document.querySelector({json.dumps(selector)});
                if (!el) return null;
                window._cdp_elements = window._cdp_elements || {{}};
                window._cdp_element_counter = window._cdp_element_counter || 0;
                const newId = ++window._cdp_element_counter;
                window._cdp_elements[newId] = el;
                return newId;
            }})()
            """
        )
        if eid is None:
            return None
        return CDPElement(self, element_id=eid)

    def locator(self, selector):
        return CDPLocator(self, selector)

    async def wait_for_timeout(self, ms):
        await asyncio.sleep(ms / 1000.0)

    async def wait_for_load_state(self, state, timeout=None):
        await asyncio.sleep(0.5)

    async def close(self):
        if self.read_task:
            self.read_task.cancel()
        if self.ws:
            await self.ws.close()
        try:
            urllib.request.urlopen(f"http://127.0.0.1:9222/json/close/{self.tab_id}")
        except Exception:
            pass
        if self.context and self in self.context.pages:
            self.context.pages.remove(self)

class CDPContext:
    def __init__(self):
        self.pages = []

    async def new_page(self):
        req_url = "http://127.0.0.1:9222/json/new"
        req = urllib.request.Request(req_url, method="PUT")
        with urllib.request.urlopen(req) as response:
            info = json.loads(response.read().decode())
        page = CDPPage(info["webSocketDebuggerUrl"], info["id"], self)
        await page.connect()
        self.pages.append(page)
        return page

    async def close(self):
        for page in list(self.pages):
            await page.close()

@asynccontextmanager
async def get_browser_context():
    context = CDPContext()
    try:
        yield context
    finally:
        await context.close()

async def human_wiggle(page, element):
    box = await element.bounding_box()
    if box:
        for _ in range(3):
            x = box['x'] + random.randint(10, int(box['width'] - 10))
            y = box['y'] + random.randint(10, int(box['height'] - 10))
            await page.mouse.move(x, y, steps=5)
            await asyncio.sleep(0.2)

async def wait_for_network_settle(page, timeout=3000):
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass
