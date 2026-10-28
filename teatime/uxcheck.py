"""合成画面と単独 HTML の UX 試験。**モデルや実データに依存させない。**"""

import argparse
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
import io
import json
from pathlib import Path
import re
import sys
import time
import uuid


URL = "http://teatime.invalid/prototype.html"
IDS = tuple(f"M{i}" for i in range(1, 10)) + ("L1", "L2", "L3")
BUTTONS = "button,[onclick],a"
CONTROLS = BUTTONS + ",input:not([type=hidden]),textarea,select"
TODAY = """() => {
 const d=new Date();
 return [d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),
 String(d.getDate()).padStart(2,'0')].join('-');
}"""

# **DOM を書き換えず、再生成した context でも同じ構造を指す。**
DOM = """
const visible=e=>!!e.getClientRects().length &&
 getComputedStyle(e).visibility!=='hidden' &&
 getComputedStyle(e).visibility!=='collapse' &&
 !e.closest('[hidden]');
const selector=e=>{
 const parts=[];
 while(e && e.nodeType===1){
  const tag=e.tagName.toLowerCase();
  const n=e.parentElement ? [...e.parentElement.children].indexOf(e)+1 : 1;
  parts.unshift(tag+':nth-child('+n+')'); e=e.parentElement;
 }
 return parts.join('>');
};
const name=e=>(e.innerText||'').replace(/\\s/g,'');
const scope=e=>e.closest('form')||e.closest('.card');
const owned=(root,query)=>[...root.querySelectorAll(query)].filter(
 e=>scope(e)===root && !e.closest('#sheet'));
const inputs=(root,b)=>owned(root,'input,textarea,select').filter(
 e=>visible(e) && e.type!=='hidden' &&
 !!(e.compareDocumentPosition(b)&Node.DOCUMENT_POSITION_FOLLOWING));
"""


class Unevaluated(Exception):
    """未評価の理由だけを運ぶ。"""


def _result(status, reason, evidence=None):
    return {"status": status, "reason": " ".join(reason.split()),
            "evidence": evidence or []}


def _aggregate(records):
    if not records:
        return _result("skip", "対象なし")
    status = next((s for s in ("fail", "skip")
                   if any(r["status"] == s for r in records)), "pass")
    reasons = list(dict.fromkeys(r["reason"] for r in records
                                if r["status"] == status))
    evidence = [e for r in records for e in r["evidence"]]
    return _result(status, " / ".join(reasons), evidence)


def _summarize(checks, coverage):
    summary = {s: sum(c["status"] == s for c in checks.values())
               for s in ("pass", "fail", "skip")}
    return {"checks": checks, "summary": summary,
            "execution": {
                "complete": summary["skip"] == 0 and not any(
                    c.get("障害") for c in coverage),
                "language": {"status": "skip", "role": "check",
                             "backend": None, "model": None, "fallback": False},
                "coverage": coverage}}


def _install_routes(context, html_bytes):
    blocked = []

    def route(request_route):
        request = request_route.request
        if request.url == URL and request.resource_type == "document":
            request_route.fulfill(status=200,
                                  content_type="text/html; charset=utf-8",
                                  body=html_bytes)
        else:
            blocked.append({"kind": request.resource_type, "遮断": True})
            request_route.abort("blockedbyclient")

    context.route("**/*", route)
    if not hasattr(context, "route_web_socket"):
        raise Unevaluated("WebSocket 遮断 API がない")

    def websocket(ws):
        # **sync API はここではデッドロックする。接続せず記録だけで遮断する。**
        blocked.append({"kind": "websocket", "遮断": True})

    context.route_web_socket("**/*", websocket)
    return blocked


@dataclass
class PageState:
    context: object
    page: object
    blocked: list
    errors: list = field(default_factory=list)
    dialogs: list = field(default_factory=list)
    attempts: int = 0


def _snapshot(page):
    return page.evaluate("() => {" + DOM + """
 const text=[];
 const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
 while(walker.nextNode()){
  const n=walker.currentNode;
  if(visible(n.parentElement) &&
     !n.parentElement.closest('script,style,noscript') && n.textContent.trim())
   text.push(n.textContent.trim());
 }
 const elements=[...document.querySelectorAll('body *')].filter(visible).map(e=>{
  const r=e.getBoundingClientRect();
  let fixed=false;
  for(let p=e;p;p=p.parentElement)
   if(getComputedStyle(p).position==='fixed'){fixed=true;break;}
  return {value:'value' in e?e.value:null,
   checked:'checked' in e?e.checked:null,disabled:!!e.disabled,
   readOnly:!!e.readOnly,
   rect:[r.x+(fixed?0:scrollX),r.y+(fixed?0:scrollY),r.width,r.height]
    .map(x=>Math.round(x*10)/10)};
 });
 return {text,elements};
}""")


def _settle(page, deadline=None):
    deadline = deadline or time.monotonic() + 3
    previous = _snapshot(page)
    while time.monotonic() + .25 <= deadline:
        page.wait_for_timeout(250)
        current = _snapshot(page)
        if current == previous:
            return current
        previous = current
    raise Unevaluated("時間切れ: 表示が収束しない")


def _fresh_page(browser, html, *, audit=None):
    context = browser.new_context(viewport={"width": 375, "height": 812},
                                  timezone_id="Asia/Tokyo",
                                  service_workers="block", accept_downloads=False)
    try:
        context.set_default_timeout(3000)
        context.set_default_navigation_timeout(3000)
        state = PageState(context, None, _install_routes(context, html.encode("utf-8")))
        if audit is not None:
            audit.append(state)

        def attach(page):
            page.on("pageerror", lambda error: state.errors.append(
                {"kind": "pageerror", "blocked": False}))

            def console(message):
                if message.type == "error":
                    # **遮断専用コードだけを除外し、一般のエラーは残す。**
                    state.errors.append({
                        "kind": "console.error",
                        "blocked": bool(state.blocked) and
                        "net::ERR_BLOCKED_BY_CLIENT" in message.text})

            page.on("console", console)

            def dialog(value):
                state.dialogs.append({"kind": value.type})
                value.dismiss()

            page.on("dialog", dialog)

        context.on("page", attach)
        state.page = context.new_page()
        deadline = time.monotonic() + 3
        state.page.goto(URL, wait_until="domcontentloaded")
        _settle(state.page, deadline)
        return state
    except Exception:
        context.close()
        raise


class Run:
    def __init__(self, browser, html, coverage):
        self.browser, self.html, self.coverage = browser, html, coverage
        self.errors = []
        self.current = None

    @contextmanager
    def fresh(self, check_id):
        audit = []
        try:
            state = _fresh_page(self.browser, self.html, audit=audit)
            self.current = state
            if state.blocked:
                raise Unevaluated("初期表示の通信を遮断")
            yield state
            if state.blocked:
                raise Unevaluated("測定中の通信を遮断")
        finally:
            for state in audit:
                self.errors.extend(state.errors)
                self.coverage.append({"check": check_id, "context": 1,
                                      "試行数": state.attempts,
                                      "遮断": list(state.blocked)})
                state.context.close()
            self.current = None


def _safe(run, check_id, action):
    try:
        return action()
    except Unevaluated as error:
        reason = str(error)
        run.coverage.append({"check": check_id, "未評価": reason,
                             "時間切れ": "時間切れ" in reason})
        return _result("skip", reason)
    except Exception as error:
        # **例外本文には入力 HTML が入ることがある。型だけを記録する。**
        run.coverage.append({"check": check_id, "障害": type(error).__name__})
        return _result("skip", "実行障害: " + type(error).__name__)


def _observe_action(state, action):
    page = state.page
    before = _settle(page)
    old_url = page.url
    dialogs = len(state.dialogs)
    blocked = len(state.blocked)
    pages = len(state.context.pages)
    deadline = time.monotonic() + 3
    state.attempts += 1
    action()
    after = _settle(page, deadline)
    if len(state.blocked) != blocked:
        raise Unevaluated("操作に伴う通信を遮断")
    if page.url.split("#")[0] != old_url.split("#")[0] or len(state.context.pages) != pages:
        raise Unevaluated("未対応遷移")
    return {"changed": before != after or len(state.dialogs) != dialogs,
            "dialogs": len(state.dialogs) - dialogs}


def _click(page, selector):
    target = page.locator(selector)
    if selector == "#sheet" or target.get_attribute("id") == "sheet":
        # **背景クリックを子要素へのクリックと取り違えない。**
        point = target.evaluate("""e=>{
         const r=e.getBoundingClientRect();
         for(let y=r.top+2;y<r.bottom;y+=20)
          for(let x=r.left+2;x<r.right;x+=20)
           if(document.elementFromPoint(x,y)===e)return {x:x-r.left,y:y-r.top};
         return null;
        }""")
        if point is None:
            raise Unevaluated("シート背景に押せる点がない")
        target.click(position=point)
    else:
        target.click()


def _open_sheet(state):
    page = state.page
    if page.locator("#fab").count() != 1 or page.locator("#sheet").count() != 1:
        raise Unevaluated("仮置きシートを開けない")
    _observe_action(state, lambda: _click(page, "#fab"))
    if not page.locator("#sheet").is_visible():
        raise Unevaluated("仮置きシートを開けない")


def _targets(page, query=BUTTONS, sheet_only=False):
    return page.evaluate("(arg)=>{" + DOM + """
 return [...document.querySelectorAll(arg.query)].filter(e=>visible(e) &&
  (!arg.sheet || !!e.closest('#sheet'))).map(e=>({
   selector:selector(e),name:name(e),disabled:!!e.disabled
 }));
}""", {"query": query, "sheet": sheet_only})


def _discover_flow(page):
    return page.evaluate("()=>{" + DOM + """
 const scopes=[...document.querySelectorAll('form,.card')].filter(
  e=>!e.closest('#sheet'));
 const flows=[];let incomplete=0;
 for(const root of scopes){
  const buttons=owned(root,'button,[onclick],a').filter(
   e=>visible(e) && ['追加','登録','保存'].includes(name(e)));
  if(!buttons.length)continue;
  const lists=owned(root,'ul,ol,tbody,[role=list]');
  if(buttons.length!==1 || lists.length!==1){incomplete++;continue;}
  const fields=inputs(root,buttons[0]);
  if(!fields.length){incomplete++;continue;}
  flows.push({button:selector(buttons[0]),inputs:fields.map(selector),
              list:selector(lists[0])});
 }
 return {flows,incomplete};
}""")


def _main_flow(run, page, check_id):
    found = _discover_flow(page)
    run.coverage.append({"check": check_id, "対象数": len(found["flows"]),
                         "不成立": found["incomplete"],
                         "曖昧": len(found["flows"]) > 1})
    if len(found["flows"]) != 1:
        raise Unevaluated("複数 flow で主 flow 未確定" if found["flows"] else "対象なし")
    return found["flows"][0]


def _corresponding(page, selector):
    return page.locator(selector).evaluate("(b)=>{" + DOM + """
 const root=scope(b);
 if(!root || b.closest('#sheet'))return null;
 const fields=inputs(root,b);
 const lists=owned(root,'ul,ol,tbody,[role=list]');
 const candidates=owned(root,'button,[onclick],a').filter(e=>visible(e) &&
  ['編集','保存','追加','登録'].includes(name(e)));
 if(!fields.length || lists.length>1 || candidates.length!==1)return null;
 return {inputs:fields.map(selector),list:lists.length?selector(lists[0]):null};
}""")


def _input_info(page, selector):
    return page.locator(selector).evaluate("""e=>({
 tag:e.tagName.toLowerCase(),type:e.type||'text',disabled:e.disabled,
 readOnly:!!e.readOnly,min:e.min,max:e.max,step:e.step,
 options:e.options?[...e.options].filter(o=>!o.disabled && o.value).map(
  o=>({value:o.value,text:o.textContent.trim()})):[],
 empty:e.options?[...e.options].some(o=>!o.disabled && o.value===''):false,
 label:e.labels?[...e.labels].map(l=>l.innerText.trim()).join(' '):''
})""")


def _fill_inputs(page, selectors, empty=False):
    values = []
    editable = 0
    radio_groups = set()
    for selector in selectors:
        info = _input_info(page, selector)
        if info["disabled"] or info["readOnly"]:
            continue
        editable += 1
        target = page.locator(selector)
        kind = info["type"]
        value, text = "", ""
        if info["tag"] == "select":
            if empty:
                if not info["empty"]:
                    raise Unevaluated("空 option がない")
            elif info["options"]:
                value = info["options"][0]["value"]
                text = info["options"][0]["text"]
            else:
                raise Unevaluated("非空 option がない")
            target.select_option(value)
        elif kind in ("checkbox", "radio"):
            group = target.get_attribute("name")
            if kind == "radio" and not empty and group:
                if group in radio_groups:
                    continue
                radio_groups.add(group)
            if empty and kind == "radio":
                target.evaluate("""e=>{
                 e.checked=false;
                 e.dispatchEvent(new Event('input',{bubbles:true}));
                 e.dispatchEvent(new Event('change',{bubbles:true}));
                }""")
            else:
                target.set_checked(not empty)
            value = not empty
            text = info["label"] if not empty else ""
            if not empty and not text:
                raise Unevaluated("選択入力の表示ラベルがない")
        elif kind in ("text", "search", "tel", "url", "email", "password",
                      "textarea", "date", "number"):
            if not empty:
                if kind == "date":
                    value = page.evaluate(TODAY)
                elif kind == "number":
                    low = Decimal(info["min"] or "0")
                    high = Decimal(info["max"]) if info["max"] else None
                    base = Decimal(info["min"] or "0")
                    step = Decimal(info["step"] if info["step"] not in ("", "any") else "1")
                    if step <= 0:
                        raise Unevaluated("数値入力の step が不正")
                    number = base + ((low - base) / step).to_integral_value(
                        rounding=ROUND_CEILING) * step
                    if high is not None and number > high:
                        number = base + ((high - base) / step).to_integral_value(
                            rounding=ROUND_FLOOR) * step
                    value = str(number)
                else:
                    token = "uxcheck-" + uuid.uuid4().hex[:12]
                    value = (token + "@example.invalid" if kind == "email" else
                             "https://example.invalid/" + token if kind == "url" else token)
                text = value
            target.fill(value)
        else:
            raise Unevaluated("未対応の入力型: " + kind)
        if not empty and not target.evaluate("e=>e.checkValidity()"):
            raise Unevaluated("入力制約に合う試験値を確定できない")
        values.append({"selector": selector, "type": kind, "value": value, "text": text})
    if not editable:
        raise Unevaluated("編集可能な入力がない")
    return values


def _items(page, selector):
    return page.locator(selector).evaluate("(root)=>{" + DOM + """
 return [...root.children].map(e=>({visible:visible(e),text:e.innerText||''}));
}""")


def _matches(item, values):
    if not item["visible"]:
        return False
    text = re.sub(r"\s+", "", item["text"])
    for value in values:
        expected = re.sub(r"\s+", "", str(value["text"]))
        if not expected:
            continue
        if value["type"] == "date":
            y, m, d = map(int, value["value"].split("-"))
            variants = (f"{y}-{m:02}-{d:02}", f"{y}/{m}/{d}", f"{y}/{m:02}/{d:02}",
                        f"{y}年{m}月{d}日", f"{m}月{d}日")
            if not any(s in text for s in variants):
                return False
        elif expected not in text:
            return False
    return True


def _button_targets(run, check_id):
    with run.fresh(check_id + ":探索") as state:
        initial = _targets(state.page)
        targets = [(t, False) for t in initial]
        hidden = state.page.locator(BUTTONS).count() - len(initial)
        run.coverage.append({"check": check_id, "除外理由": "初期は非表示",
                             "件数": hidden})
        try:
            _open_sheet(state)
            targets.extend((t, True) for t in _targets(state.page, sheet_only=True))
        except Unevaluated as error:
            run.coverage.append({"check": check_id, "未評価": str(error)})
            return targets, [_result("skip", str(error))]
        return targets, []


def _check_m1(run):
    targets, records = _button_targets(run, "M1")
    attempts = 0
    for target, opened in targets:
        def measure():
            nonlocal attempts
            with run.fresh("M1") as state:
                if opened:
                    _open_sheet(state)
                locator = state.page.locator(target["selector"])
                evidence = [{"selector": target["selector"], "sheet": opened}]
                if locator.count() != 1 or not locator.is_visible():
                    return _result("skip", "前提再現不能", evidence)
                if locator.is_disabled():
                    return _result("skip", "disabled のため押せない", evidence)
                attempts += 1
                observed = _observe_action(
                    state, lambda: _click(state.page, target["selector"]))
                return _result("pass" if observed["changed"] else "fail",
                               "可視変化あり" if observed["changed"] else "押しても変化なし",
                               evidence)
        records.append(_safe(run, "M1", measure))
    run.coverage.append({"check": "M1", "対象数": len(targets), "試行数": attempts})
    return _aggregate(records)


def _check_m2(run):
    targets, records = _button_targets(run, "M2")
    targets = [(t, opened) for t, opened in targets
               if t["name"] in ("編集", "保存", "追加", "登録")]
    attempts = 0
    for target, opened in targets:
        def measure():
            nonlocal attempts
            with run.fresh("M2") as state:
                page = state.page
                if opened:
                    _open_sheet(state)
                relation = _corresponding(page, target["selector"])
                if relation is None:
                    raise Unevaluated("対応入力が曖昧")
                if page.locator(target["selector"]).is_disabled():
                    raise Unevaluated("disabled のため押せない")
                if target["name"] != "編集":
                    _fill_inputs(page, relation["inputs"])
                before = len(_items(page, relation["list"])) if relation["list"] else 0
                attempts += 1
                _observe_action(state, lambda: _click(page, target["selector"]))
                editable = all(not (i["disabled"] or i["readOnly"]) for i in
                               (_input_info(page, s) for s in relation["inputs"]))
                after = len(_items(page, relation["list"])) if relation["list"] else 0
                passed = editable or (relation["list"] is not None and after == before + 1)
                return _result("pass" if passed else "fail",
                               "編集可能または1件追加" if passed else "編集できず追加もない",
                               [{"selector": target["selector"], "editable": editable,
                                 "before": before, "after": after}])
        records.append(_safe(run, "M2", measure))
    run.coverage.append({"check": "M2", "対象数": len(targets), "試行数": attempts})
    return _aggregate(records)


def _check_m3(run):
    with run.fresh("M3") as state:
        page = state.page
        flow = _main_flow(run, page, "M3")
        _fill_inputs(page, flow["inputs"], empty=True)
        before = len(_items(page, flow["list"]))
        observed = _observe_action(state, lambda: _click(page, flow["button"]))
        invalid = sum(page.locator(s).evaluate(
            "e=>e.matches(':invalid') && !!e.validationMessage") for s in flow["inputs"])
        after = len(_items(page, flow["list"]))
        passed = observed["changed"] or bool(invalid)
        return _result("pass" if passed else "fail",
                       ("空行追加あり" if after > before else "空入力への応答あり")
                       if passed else "空入力にメッセージも可視変化もない",
                       [{"invalid": invalid, "dialogs": observed["dialogs"],
                         "before": before, "after": after}])


@dataclass
class FlowState:
    state: PageState
    flow: dict
    values: list
    item: dict


def _check_m4(run, state):
    page = state.page
    flow = _main_flow(run, page, "M4")
    values = _fill_inputs(page, flow["inputs"])
    before = _items(page, flow["list"])
    _observe_action(state, lambda: _click(page, flow["button"]))
    after = _items(page, flow["list"])
    remaining = list(after)
    for item in before:
        if item in remaining:
            remaining.remove(item)
    matching = [item for item in remaining if _matches(item, values)]
    passed = len(after) == len(before) + 1 and len(matching) == 1
    result = _result("pass" if passed else "fail",
                     "投入値を含む項目が1件増えた" if passed else "投入値を含む1件追加が成立しない",
                     [{"selector": flow["list"], "before": len(before),
                       "after": len(after), "matching": len(matching)}])
    return result, FlowState(state, flow, values, matching[0] if passed else {})


def _loss_explanation(page):
    texts = page.locator("#sheet .as").evaluate_all(
        "(es)=>{" + DOM + "return es.filter(visible).map(e=>e.innerText);}")
    uncertain = []
    for text in texts:
        if not re.search(r"再読み込み|リロード|ページを更新", text):
            continue
        sentences = re.split(r"[。\n]", text)
        for sentence in sentences:
            if re.search(r"消えません|消えない|消えることはありません|消えることはない|"
                         r"失われません|失われない|保持されます|"
                         r"消えるわけでは|消えるとは限", sentence):
                continue
            if re.search(r"消えます|消える|失われます|保持されません", sentence):
                if re.search(r"かもしれ|場合|可能性|でしょう|[?？]|ない", sentence):
                    uncertain.append(text[:180])
                else:
                    return _result("pass", "再読み込みで消えることを仮置きに明示")
        if not re.search(r"消え|失わ|保持", text):
            uncertain.append(text[:180])
    if uncertain:
        return _result("skip", "項目が消えるが消失説明を確定できない",
                       [{"候補文": t} for t in uncertain])
    return _result("fail", "再読み込みで項目が消えるが消失説明がない")


def _check_m5(run, flow_state):
    state = flow_state.state
    page = state.page
    response = page.reload(wait_until="domcontentloaded", timeout=3000)
    if (response is None or response.status != 200 or
            response.body() != run.html.encode("utf-8")):
        return _result("skip", "同じ HTML を再読込できない")
    _settle(page)
    if state.blocked:
        raise Unevaluated("再読込時の通信を遮断")
    if any(_matches(item, flow_state.values)
           for item in _items(page, flow_state.flow["list"])):
        return _result("pass", "再読み込み後も追加項目が残る")
    try:
        _open_sheet(state)
    except Unevaluated:
        return _result("skip", "項目が消えるが仮置きシートを開けない")
    return _loss_explanation(page)


def _check_m6(run):
    records = []
    with run.fresh("M6") as state:
        page = state.page
        for opened in (False, True):
            if opened:
                try:
                    _open_sheet(state)
                except Unevaluated as error:
                    records.append(_result("skip", str(error)))
                    break
            dimensions = page.evaluate("""()=>({
             scrollWidth:document.documentElement.scrollWidth,
             clientWidth:document.documentElement.clientWidth
            })""")
            overflow = dimensions["scrollWidth"] > dimensions["clientWidth"] + 1
            records.append(_result("fail" if overflow else "pass",
                                   "横にはみ出す" if overflow else "横はみ出しなし",
                                   [dict(dimensions, sheet=opened)]))
            targets = _targets(page, CONTROLS)
            attempts = 0
            for target in targets:
                if target["disabled"]:
                    continue
                locator = page.locator(target["selector"])
                locator.scroll_into_view_if_needed()
                box = locator.bounding_box()
                evidence = {"selector": target["selector"], "sheet": opened}
                if not box:
                    records.append(_result("skip", "可視だが矩形を取得できない", [evidence]))
                    continue
                attempts += 1
                small = box["width"] < 40 or box["height"] < 40
                evidence.update(width=round(box["width"], 2), height=round(box["height"], 2))
                records.append(_result("fail" if small else "pass",
                                       "押せる要素が40px未満" if small else "40px以上",
                                       [evidence]))
            run.coverage.append({"check": "M6", "sheet": opened,
                                 "対象数": len(targets), "試行数": attempts,
                                 "除外理由": "非表示・disabled",
                                 "除外数": page.locator(CONTROLS).count() - attempts})
    return _aggregate(records)


def _check_m7(run):
    with run.fresh("M7") as state:
        page = state.page
        if any(page.locator(s).count() != 1 for s in ("#fab", "#sheet", "#sclose")):
            return _result("fail", "仮置き枠の要素が欠落または重複")
        sheet = page.locator("#sheet")
        initial = not sheet.evaluate("e=>e.classList.contains('on')") and not sheet.is_visible()
        _observe_action(state, lambda: _click(page, "#fab"))
        opened = sheet.evaluate("e=>e.classList.contains('on')") and sheet.is_visible()
        if not opened:
            return _result("fail", "仮置きシートが開かない")
        _observe_action(state, lambda: _click(page, "#sclose"))
        closed = not sheet.evaluate("e=>e.classList.contains('on')") and not sheet.is_visible()
        return _result("pass" if initial and closed else "fail",
                       "仮置きシートを開閉できる" if initial and closed else "仮置きシートの開閉不成立",
                       [{"initial": initial, "opened": opened, "closed": closed}])


def _check_m8(run):
    errors = sum(not error["blocked"] for error in run.errors)
    blocked = sum(error["blocked"] for error in run.errors)
    return _result("fail" if errors else "pass",
                   "JavaScript エラーあり" if errors else "JavaScript エラーなし",
                   [{"errors": errors, "blocked_errors": blocked}])


def _check_m9(run):
    for _ in range(2):
        with run.fresh("M9") as state:
            page = state.page
            today = page.evaluate(TODAY)
            values = page.locator("input[type=date]").evaluate_all(
                "es=>es.map(e=>e.value)")
            if today != page.evaluate(TODAY):
                continue
            run.coverage.append({"check": "M9", "対象数": len(values),
                                 "試行数": len(values)})
            return _aggregate([
                _result("pass" if value in ("", today) else "fail",
                        "日付は空または今日" if value in ("", today) else "初期日付が今日ではない",
                        [{"index": i, "value": value, "today": today}])
                for i, value in enumerate(values)])
    raise Unevaluated("日付が測定中に変わった")


def _collect_language(state):
    """**試験値を入れない独立 context だけで材料を集める。**"""
    initial = _snapshot(state.page)["text"]
    _open_sheet(state)
    sheet = state.page.locator("#sheet").inner_text()
    return {"initial": initial, "sheet": sheet}


def check(html: str, *, transcript=None, structured=None, assumptions=None,
          language=False) -> dict:
    checks = {key: _result("skip", "T1aでは未実施" if key.startswith("L")
                          else "ブラウザ未起動") for key in IDS}
    coverage = []
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                run = Run(browser, html, coverage)
                for key, function in (("M1", _check_m1), ("M2", _check_m2),
                                      ("M3", _check_m3)):
                    checks[key] = _safe(run, key, lambda f=function: f(run))

                def persistence():
                    with run.fresh("M4/M5") as state:
                        result, flow = _check_m4(run, state)
                        checks["M4"] = result
                        checks["M5"] = (_safe(run, "M5", lambda: _check_m5(run, flow))
                                        if result["status"] == "pass" else
                                        _result("skip", "M4 非 pass のため未実施"))
                    return checks["M4"]

                checks["M4"] = _safe(run, "M4", persistence)
                if checks["M4"]["status"] != "pass":
                    checks["M5"] = _result("skip", "M4 非 pass のため未実施")
                for key, function in (("M6", _check_m6), ("M7", _check_m7),
                                      ("M9", _check_m9)):
                    checks[key] = _safe(run, key, lambda f=function: f(run))
                checks["M8"] = _check_m8(run)
            finally:
                browser.close()
    except Exception as error:
        coverage.append({"check": "browser", "障害": type(error).__name__})
        for key in IDS[:9]:
            if checks[key]["reason"] == "ブラウザ未起動":
                checks[key] = _result("skip", "ブラウザ起動・実行障害: " + type(error).__name__)
    return _summarize(checks, coverage)


def _path(value, *, output=False):
    resolved = Path(value).expanduser().resolve()
    repo = Path(__file__).resolve().parent.parent
    if any(resolved.is_relative_to(repo / name) for name in ("out", "samples", ".certs")):
        raise ValueError("禁止ディレクトリ内のパス")
    if output and not resolved.is_relative_to(Path("/tmp").resolve()):
        raise ValueError("保存先は /tmp/ 配下のみ")
    return resolved


def write_report(report: dict, destination: Path) -> Path:
    destination = _path(destination, output=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    return destination


def print_failures(report: dict, stream=None) -> int:
    stream = sys.stdout if stream is None else stream
    count = 0
    for key in IDS:
        record = report["checks"][key]
        if record["status"] == "fail":
            print(key, "fail", " ".join(record["reason"].split()), file=stream)
            count += 1
    return count


def _synthetic_case(kind):
    from .prototype import CSS, SHEET_JS, _sheet

    if kind not in ("good", "bad"):
        raise ValueError("合成の種類が不正")
    good = kind == "good"
    assumptions = [{"gap": "開始時の一覧は未決定",
                    "assumption": "例を置かず空一覧から始める",
                    "why": "確認項目を1件追加する操作を確かめるため",
                    "risk": "low", "how_to_check": "入力して追加する"}]
    markup = """
<main><h1>確認項目を入力して追加してください</h1>
<div class="card">
 <label>確認項目<input id="entry" type="text"></label>
 <label>日付<input id="day" type="date"></label>
 <button id="add">追加</button><ul id="entries"></ul><p id="message"></p>
</div>
<div class="card"><label>補助入力<input id="extra" type="text" value="補助" readonly></label>
 <button id="edit">編集</button><p id="editmessage"></p></div>
<div class="card"><button id="confirm">確認</button><p id="confirmed"></p>
 <a href="#help" id="link">説明</a><p id="help"></p></div></main>
"""
    script = """
const entry=document.getElementById('entry'),day=document.getElementById('day');
const entries=document.getElementById('entries'),message=document.getElementById('message');
const now=new Date();
DAY_OFFSET
day.value=[now.getFullYear(),String(now.getMonth()+1).padStart(2,'0'),
 String(now.getDate()).padStart(2,'0')].join('-');
let rows=JSON.parse(localStorage.getItem('ux-items')||'[]');
function render(){
 entries.replaceChildren();
 for(const row of rows){
  const li=document.createElement('li');li.textContent=row.text+' '+row.date;
  entries.appendChild(li);
 }
}
render();
document.getElementById('add').onclick=()=>{
 if(!entry.value.trim()||!day.value){EMPTY_ACTION return;}
 rows.push({text:entry.value,date:day.value});
 localStorage.setItem('ux-items',JSON.stringify(rows));
 render();message.textContent='追加しました';
};
document.getElementById('edit').onclick=()=>{
 const extra=document.getElementById('extra');
 EDIT_ACTION
};
document.getElementById('confirm').onclick=()=>{CONFIRM_ACTION};
document.getElementById('link').onclick=()=>{
 document.getElementById('help').textContent='確認項目と日付を入力して追加します';
};
"""
    script = script.replace("DAY_OFFSET", "" if good else "now.setDate(now.getDate()-1);")
    script = script.replace("EMPTY_ACTION",
                            "message.textContent='確認項目を入力してください';" if good else "")
    script = script.replace("EDIT_ACTION",
                            "extra.readOnly=false;document.getElementById('editmessage').textContent='編集できます';"
                            if good else
                            "extra.disabled=true;document.getElementById('editmessage').textContent='編集を停止しました';")
    script = script.replace("CONFIRM_ACTION",
                            "document.getElementById('confirmed').textContent='確認しました';"
                            if good else "")
    size = ("button,input,a{min-width:44px;min-height:44px}"
            "input{max-width:100%}a{display:inline-block;padding:8px}")
    if not good:
        size += "#confirm{width:24px;height:24px;min-width:0;min-height:0;padding:0;font-size:10px}"
    html = ('<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>確認項目</title><style>{CSS}{size}</style></head><body>"
            + markup + _sheet(assumptions) + f"<script>{script}\n{SHEET_JS}</script></body></html>")
    return {"html": html, "transcript": "確認項目を1件追加する画面を確かめる。",
            "structured": {"decision": "確認項目と日付を入力して追加する"},
            "assumptions": assumptions}


def _verify_synthetic():
    """受入専用。**失敗を通常の skip に変えない。**"""
    from unittest.mock import patch
    import tempfile
    from . import model

    good = _synthetic_case("good")["html"]
    bad = _synthetic_case("bad")["html"]
    multiple = good.replace("</main>", """
<div class="card"><input type="text"><button>保存</button><ul></ul></div></main>""")
    with patch.object(model, "ask", side_effect=AssertionError("model.ask 呼出し")) as ask, \
            patch.object(model, "ask_json", side_effect=AssertionError("model.ask_json 呼出し")) as ask_json, \
            patch.object(model, "reset_usage", side_effect=AssertionError("usage reset")) as reset:
        reports = []
        for html, failed in ((good, set()), (bad, {"M1", "M2", "M3", "M6", "M9"})):
            report = check(html, language=True)
            reports.append(report)
            actual = {k for k, v in report["checks"].items() if v["status"] == "fail"}
            assert actual == failed, ("fail 集合", actual, failed)
            for key in IDS[:9]:
                if key not in failed:
                    record = report["checks"][key]
                    assert record["status"] == "pass", (
                        key + ": " + record["status"] + " " + record["reason"])
            assert all(report["checks"][k]["status"] == "skip" for k in IDS[9:])

        # **sync Playwright の入れ子による起動障害を、期待した skip と誤認しない。**
        report = check(multiple)
        for key in ("M3", "M4", "M5"):
            record = report["checks"][key]
            assert record["status"] == "skip", (key, record)
            assert record["reason"] == (
                "M4 非 pass のため未実施" if key == "M5" else
                "複数 flow で主 flow 未確定"), (key, record)

        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                no_save = good.replace("localStorage.setItem('ux-items',JSON.stringify(rows));", "")
                for sentence, expected in (
                    ("再読み込みすると入力した項目は消えます。", "pass"),
                    ("", "fail"),
                    ("再読み込みしても入力した項目は消えません。", "fail"),
                    ("再読み込みで消えることはありません。", "fail"),
                ):
                    html = no_save.replace("例を置かず空一覧から始める",
                                           "例を置かず空一覧から始める。" + sentence)
                    run = Run(browser, html, [])
                    with run.fresh("境界M5") as state:
                        result, flow = _check_m4(run, state)
                        assert result["status"] == "pass", result
                        result = _check_m5(run, flow)
                        assert result["status"] == expected, result
                        assert "消える" in result["reason"], result

                run = Run(browser, good, [])
                with run.fresh("reload応答") as state:
                    result, flow = _check_m4(run, state)
                    assert result["status"] == "pass"
                    with patch.object(state.page, "reload", return_value=None):
                        assert _check_m5(run, flow)["status"] == "skip"
                    state.context.unroute("**/*")
                    state.context.route("**/*", lambda route: route.fulfill(
                        status=200, content_type="text/html", body="<html>別 HTML</html>"))
                    assert _check_m5(run, flow)["status"] == "skip"

                with run.fresh("閉じる探索") as state:
                    close_selector = state.page.locator("#sclose").evaluate(
                        "(e)=>{" + DOM + "return selector(e);}")
                # **同じ good の測定結果を再利用し、開閉別の証拠は引き続き確かめる。**
                for key in ("M1", "M6"):
                    result = reports[0]["checks"][key]
                    evidence = [e for e in result["evidence"] if e.get("selector") == close_selector]
                    assert evidence and all(e["sheet"] for e in evidence), evidence

                multiple_run = Run(browser, multiple, [])
                with multiple_run.fresh("複数flow") as state:
                    assert len(_discover_flow(state.page)["flows"]) == 2

                state = _fresh_page(browser, good)
                try:
                    state.page.evaluate("""()=>{
                     fetch('https://external.invalid/test').catch(()=>{});
                     new WebSocket('wss://external.invalid/socket');
                    }""")
                    _settle(state.page)
                    kinds = {b["kind"] for b in state.blocked}
                    assert {"fetch", "websocket"} <= kinds, kinds
                finally:
                    state.context.close()

                with run.fresh("M4値") as state:
                    result, flow = _check_m4(run, state)
                    assert result["status"] == "pass"
                    values = [v["text"] for v in flow.values if v["type"] == "text"]
                with run.fresh("L材料") as state:
                    materials = json.dumps(_collect_language(state), ensure_ascii=False)
                    assert values and all(v not in materials for v in values)
            finally:
                browser.close()
        ask.assert_not_called()
        ask_json.assert_not_called()
        reset.assert_not_called()

    repo = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory(prefix="teatime-ux-boundary-", dir="/tmp") as directory:
        for name in ("out", "samples", ".certs"):
            link = Path(directory) / name
            link.symlink_to(repo / name, target_is_directory=True)
            for path in (repo / name / "never-open.html", link / "never-open.html"):
                with patch.object(Path, "open", side_effect=AssertionError("禁止入力を開いた")) as opened:
                    with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                        result = main([str(path), "--output", str(Path(directory) / "report.json")])
                    assert result == 2, result
                    opened.assert_not_called()


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def main(argv=None) -> int:
    parser = _Parser(description="HTML の UX 試験（T1a）")
    parser.add_argument("html", nargs="?")
    parser.add_argument("--synthetic", choices=("good", "bad"))
    parser.add_argument("--write-synthetics", metavar="DIRECTORY")
    parser.add_argument("--verify-synthetic", action="store_true")
    parser.add_argument("--output", metavar="JSON")
    try:
        args = parser.parse_args(argv)
    except ValueError as error:
        print("引数不正: " + str(error), file=sys.stderr)
        return 2
    except SystemExit as error:
        return int(error.code)
    modes = (args.html is not None, args.synthetic is not None,
             args.write_synthetics is not None, args.verify_synthetic)
    if sum(modes) != 1:
        print("入力モードは1つだけ指定してください", file=sys.stderr)
        return 2
    if (args.write_synthetics or args.verify_synthetic) and args.output:
        print("このモードに --output は指定できません", file=sys.stderr)
        return 2
    if args.verify_synthetic:
        try:
            _verify_synthetic()
            return 0
        except Exception as error:
            detail = str(error) if isinstance(error, AssertionError) else type(error).__name__
            print("合成境界確認失敗: " + " ".join(detail.split()),
                  file=sys.stderr)
            return 1
    try:
        if args.write_synthetics:
            directory = _path(args.write_synthetics, output=True)
            destinations = [_path(directory / (kind + ".html"), output=True)
                            for kind in ("good", "bad")]
            directory.mkdir(parents=True, exist_ok=True)
            for kind, destination in zip(("good", "bad"), destinations):
                destination.write_text(_synthetic_case(kind)["html"], encoding="utf-8")
            return 0
        if not args.output:
            raise ValueError("--output が必要")
        destination = _path(args.output, output=True)
        if args.synthetic:
            report = check(**_synthetic_case(args.synthetic))
        else:
            source = _path(args.html)
            if source == destination:
                raise ValueError("入力と保存先は別にしてください")
            report = check(source.read_text(encoding="utf-8"))
        write_report(report, destination)
    except (OSError, ValueError) as error:
        print(str(error) if isinstance(error, ValueError) else
              "読込・保存失敗: " + type(error).__name__, file=sys.stderr)
        return 2
    if print_failures(report):
        return 1
    return 0 if report["execution"]["complete"] else 2


if __name__ == "__main__":
    sys.exit(main())
