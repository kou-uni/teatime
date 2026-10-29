"""5つ目の成果物 — **動くプロトタイプそのもの。**

仕様書ではなく、ブラウザで開けば動く1枚の HTML を出す。

**ここだけ「空白を埋めない」規則を外す。**
文書（pitch/product/project/feedback）は議論に無いことを埋めない。
**作るものは、埋めないと存在できない。** だから仮置きして前に進み、
**どこを仮置きしたかをプロトタイプ自身が表示する。**

## 作り方（2026-10-28 に変更）
以前は「1枚の HTML を丸ごと LLM に書かせる」ことにしていたが、
**長い出力は応答側の長さガードに引っかかって返ってこない。**
いまは **枠（doctype/CSS/ヘッダ/仮置きシート）を Python が決め打ちし、
LLM には中身だけを短く2回に分けて書かせる。**
仮置きの表示が LLM の気分で消えないのも、この分け方の利点。
"""
import html as _h
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile

from . import deliver, model

ASSUME_SYS = (
    "あなたは、議論の記録と抽出結果を渡されて、**作り始めるために必要な仮置き**を決める人です。"
    "議論で決まっていないことを、**決めたことにしない。** "
    "『いまは仮にこうしておく』を、理由つきで置くのが仕事です。出力は JSON のみ。"
)

ASSUME_PROMPT = """次の議論から**プロトタイプを1本作る**ために、
決まっていないことへ**仮置き**を置いてください。

規則
- **採った案と成り立つ条件は動かさない。** 仮置きはその外側だけ
- 仮置きは**最大7つ**。多く置かない。置くほど、確かめる相手が減ります
- 各仮置きに `risk` を付ける: `high` = これが外れると作り直し / `low` = 後から変えられる
- **議論で既に決まっていることを仮置きに入れない**

出力:
{{"mvp":"プロトタイプで実際に動かす一本（1文）",
"assumptions":[{{"gap":"決まっていないこと","assumption":"仮にこうする",
"why":"そう置いた理由","risk":"high|low","how_to_check":"これを確かめる一番安い方法"}}]}}

---
{core}
"""

# --- 1回目: 画面の中身（マークアップだけ） ---------------------------------

MARKUP_SYS = (
    "あなたは、動くプロトタイプの**画面の中身だけ**を書く実装者です。\n"
    "- 出力は `<main>` の中に入る HTML 断片のみ。"
    "doctype・html・head・style・script は**書かない**（別で用意されます）。\n"
    "- class は `card` `row` `col` `btn` `btn2` `mut` `tag` `big` `field` だけ使う。"
    "自前の style 属性は最小限。\n"
    "- **読むだけの画面にしない。** 入力欄・ボタン・一覧など、指で触れるものを置く。\n"
    "- 空の画面は出さない。ただし**例の行は2件まで**。行の頭に `<span class=\"tag\">例</span>` を付け、"
    "議論の記録か仮置きに出てくる言葉だけで書く（作り話を本物に見せない）。\n"
    "- **議論で後回しにしたもの（次回やると決めたこと）は、画面に出さない。**\n"
    "- `<main>` タグ自体は書かない（中身だけ）。\n"
    "- 操作に必要な要素には `id` を付ける（JS から触ります）。\n"
    "- 絵文字を使わない。日本語。\n"
    "- **2500字以内。** 前置き・後書き・コードフェンスを書かない。"
)

MARKUP_PROMPT = """## 作るもの
{mvp}

## 守ること（議論で決まっている。動かさない）
- 採った案: {adopted}
- 成り立つ条件: {condition}
- 手放した価値: {sacrificed}
  → **手放したものを作り足さないこと。** これを守るのが、この画面の仕事です

## 仮置き（議論では決まっていない前提。これに沿って作る）
{assumptions}

## 議論の記録（抜粋）
{transcript}

---
`<main>` の中身を 2500字以内で出してください。
"""

# --- 2回目: 動き（JS だけ） ------------------------------------------------

JS_SYS = (
    "あなたは、与えられた HTML を**実際に動かす JavaScript だけ**を書く実装者です。\n"
    "- 出力は素の JS のみ。`<script>` タグもコードフェンスも書かない。\n"
    "- 外部ライブラリを使わない。保存が要るなら localStorage。\n"
    "- 渡された HTML に**実在する id/class だけ**を触る。無いものを作らない。\n"
    "- 主要な操作が1つでも実際に効くこと（増える・消える・絞られる・計算される）。\n"
    "- **押したら必ず目に見えて何か変わる。** 空のまま押されたら、その場で一言出す。\n"
    "- 日付の既定値は今日。\n"
    "- **2000字以内。** 説明文を書かない。"
)

JS_PROMPT = """この画面を動かしてください。作っているもの: {mvp}

```html
{markup}
```

---
JS だけを 2000字以内で。
"""

JS_FIX_PROMPT = """
前回の JS は構文エラーで動きませんでした。**エラーを直した JS 全体**を、もう一度出してください。
{err}
"""

CSS = """
:root{color-scheme:light dark;--paper:#f4f1ea;--ink:#23201c;--muted:#6f6a60;--rule:#ded8c9;--red:#9b3b2f;--main:#3f6b26;--on-main:#f4f1ea;--ui:-apple-system,BlinkMacSystemFont,"Hiragino Sans","Hiragino Kaku Gothic ProN","Noto Sans JP","Yu Gothic Medium",sans-serif;--num:ui-rounded,-apple-system,"SF Pro Rounded","Hiragino Sans","Noto Sans JP",sans-serif;--tap-in:70ms;--tap-out:180ms;--settle:cubic-bezier(.34,1.56,.64,1)}
@media(prefers-color-scheme:dark){:root{--paper:#14130f;--ink:#e9e4d8;--muted:#948d80;--rule:#2e2a23;--red:#d08477;--main:#7fb34a;--on-main:#14130f}}
/* 角丸は役割。読むものは0、**指で触れるものだけ 10px**、バーは完全な丸端。
   ポケモンGO 実測の逆転（一覧カード19pt／詳細シート5.7pt）＝
   小さい板はつまめるモノ、大きい板は下敷き。だから面には足さない。 */
*{box-sizing:border-box;border-radius:0!important;letter-spacing:normal}
*::before,*::after,input::file-selector-button{border-radius:0!important}
body,h1,h2,h3,h4,p,ul,ol,dl,dd,blockquote,pre,fieldset{margin:0}
*+*{margin-top:16px}
body{margin:0;background:var(--paper);color:var(--ink);font:500 16px/1.6 var(--ui);overflow-wrap:anywhere;-webkit-text-size-adjust:100%;-webkit-tap-highlight-color:transparent}
body>header,main{width:100%;max-width:704px;margin-inline:auto;padding:32px}
body>header{padding-bottom:16px;color:var(--muted);font-size:12px;border-bottom:1px solid var(--rule)}
main{margin-top:0;padding-bottom:88px}
body{padding-bottom:64px}
/* 明朝は全廃。この画面は読むためではなく触るためにある。 */
h1{font:800 30px/1.35 var(--ui)}
h2,.big{font-size:23px;font-weight:800;line-height:1.5}
h3{font-size:19px;font-weight:800}h4{font-size:17px;font-weight:800}
strong,b{font-weight:800}
main>:is(div,section,article,form)+:is(div,section,article,form){margin-top:56px}
.card,blockquote{background:none;border:0;padding:0}
.row{display:flex;flex-wrap:wrap;align-items:center;gap:16px}
.col{display:flex;flex-direction:column;gap:16px}
.row>*,.col>*{margin-top:0;min-width:0;max-width:100%}
.row>input:not([type=radio]):not([type=checkbox]){flex:1 1 100%}
.row>.btn{flex:1 1 100%}
.row>.btn2{flex:0 1 auto}
.mut,.tag{color:var(--muted);font-size:14px}.tag{font-size:12px;font-weight:700}
ul,ol{padding-left:28px}li+li{margin-top:8px}
dt{font-weight:800}dd{margin-top:4px}
fieldset{min-width:0;padding:0;border:0}legend{padding:0;font-weight:800}
label{display:block}label>input,label>select,label>textarea{margin-top:8px}
pre{white-space:pre-wrap;overflow-wrap:anywhere}pre,code,kbd,samp{font-family:var(--ui);font-size:14px}
img,video,canvas,svg{max-width:100%;height:auto}
/* 数字は ui-rounded（SF Pro Rounded・標準搭載）で桁を揃える。
   本家も和文と数字で丸みが別。ダウンロードは1バイトも増えない。 */
table,output,time,progress,meter,.big{font-variant-numeric:tabular-nums}
table{width:100%;table-layout:fixed;border-collapse:collapse;font:14px/1.6 var(--ui)}
th,td{padding:10px 8px;text-align:left;vertical-align:top;border-bottom:1px solid var(--rule)}
th{font-weight:800;font-size:12px;color:var(--muted)}caption{text-align:left;margin-bottom:8px;font-weight:800}
/* バーだけは高さの半分で丸める（ポケモンGO: バーは全部これ）。 */
progress,meter,[role=progressbar]{border-radius:999px!important;overflow:hidden}
a{display:inline-flex;align-items:center;min-width:44px;min-height:44px;padding:8px 0;color:inherit;text-underline-offset:4px;touch-action:manipulation}
/* 入力は薄い沈み。触っている間だけ下罫が Main に変わる＝
   「触れた対象そのものが変化する」。リップルは要らない（押した場所は本人が知っている）。 */
input,textarea,select,.field{display:block;width:100%;max-width:100%;min-width:44px;min-height:48px;font:inherit;color:var(--ink);padding:10px 16px;border:0;border-bottom:2px solid var(--rule);background:color-mix(in srgb,var(--ink) 4%,var(--paper));transition:border-color 120ms ease-out,background 120ms ease-out}
input:focus,textarea:focus,select:focus{border-bottom-color:var(--main);background:color-mix(in srgb,var(--ink) 7%,var(--paper));outline:none}
textarea{resize:vertical}input::placeholder,textarea::placeholder{color:var(--muted);opacity:1}
input:is([type=radio],[type=checkbox]){appearance:none;display:inline-block;width:44px;height:44px;padding:8px;margin:0;vertical-align:middle;border:1px solid var(--ink);background:var(--paper);flex-shrink:0;cursor:pointer}
input[type=radio]:checked::before,input[type=checkbox]:checked::before{content:"✓";display:block;text-align:center;color:var(--ink);font:800 20px/1.3 var(--ui)}

/* ===== 押す ==================================================================
   色は2値しかない。**Main＝進む / 紙＝退く・選ぶ**（ウマ娘にはこの2つしかなく、
   赤い危険ボタンすら無い）。色を増やすのではなく、既にあった墨の面を Main に塗り替えた
   ので、色数は増えていない。
   影は blur 0 のハード影＝「ぼけた浮き」ではなく**板の厚み**。押すと 3px→1px に縮む。
   触れる前に「押せば沈む」を予告しているのはこの厚みで、装飾ではない。 */
button,[role=button],input[type=submit],input[type=button],input[type=reset],.btn,input::file-selector-button{display:inline-flex;align-items:center;justify-content:center;width:auto;min-width:44px;min-height:48px;max-width:100%;padding:10px 20px;border:1px solid var(--main);border-radius:10px!important;background:var(--main);color:var(--on-main);font:inherit;font-weight:800;cursor:pointer;text-decoration:none;text-align:center;touch-action:manipulation;white-space:normal;box-shadow:0 3px 0 color-mix(in srgb,#000 42%,var(--main));transition:transform var(--tap-out) var(--settle),box-shadow var(--tap-out) ease-out,filter var(--tap-out) ease-out}
.btn2{background:none;color:var(--ink);border:0;border-radius:0!important;border-bottom:2px solid var(--ink);padding:8px 0;box-shadow:none;font-weight:800}
label:has(input[type=radio]),label:has(input[type=checkbox]),select,summary,[role=option],.row:has(>.btn2~.btn2)>.btn2,label.btn2{min-width:44px;min-height:48px;padding:10px 16px;border:1px solid var(--ink);border-radius:10px!important;background:var(--paper);color:var(--ink);cursor:pointer;box-shadow:none}
label:has(input[type=radio]),label:has(input[type=checkbox]){display:flex;align-items:center;gap:8px}
label:has(input[type=radio])>*,label:has(input[type=checkbox])>*{margin-top:0}
summary{display:list-item}option{background:var(--paper);color:var(--ink)}
.row:has(>.btn2~.btn2)>.btn2{flex:1 1 100%;justify-content:flex-start;text-align:left}
select{appearance:none;background-image:none}
/* 押下。scale(.94) は4本の分解で全部一致した唯一の値。70ms で沈め、影を潰す。 */
:is(button,[role=button],input[type=submit],input[type=button],input[type=reset],.btn,.btn2,summary,label:has(input[type=radio]),label:has(input[type=checkbox]),[role=option],.filepick):active{transform:scale(.94);filter:brightness(.93);box-shadow:0 1px 0 color-mix(in srgb,#000 42%,var(--main));transition-duration:var(--tap-in);transition-timing-function:cubic-bezier(.4,0,1,1)}
:is(summary,label:has(input[type=radio]),label:has(input[type=checkbox]),[role=option],.btn2){transition:transform var(--tap-out) var(--settle),background 120ms ease-out}
/* 離した瞬間に 1.00 を追い越して戻る。縮むだけだと「へこんだ」で終わる。
   :active の戻り transition では出せない——移動量が 6% しかないので、
   曲線が 10% 跳ねても見かけは 0.6% で消える。だから keyframes を1本流す。 */
@keyframes tapback{0%{transform:scale(.94);animation-timing-function:cubic-bezier(.16,1,.3,1)}50%{transform:scale(1.05);animation-timing-function:cubic-bezier(.33,0,.67,1)}100%{transform:scale(1)}}
.tapback{animation:tapback 180ms both}
:where(button,input,textarea,select,a,summary,[tabindex],[role=button]):focus-visible{outline:3px solid var(--ink);outline-offset:3px}
/* 無効は取り消し線をやめ、**地の色に沈める**（ツムツムは無効をグレーにせず地の青に沈める）。
   厚みを外すので「押せない」が形で分かる。線を引くと「あった物を消した」に読める。 */
:disabled,[aria-disabled=true]{cursor:not-allowed;background:color-mix(in srgb,var(--ink) 5%,var(--paper))!important;color:var(--muted)!important;border-color:transparent!important;box-shadow:none!important;text-decoration:none;filter:none}
/* 選ばれたものは Main に反転する。選ぶ＝進む側だから色は同じでいい。
   なった瞬間に 160ms だけ跳ねる（:has が一致した瞬間に animation が走る）。 */
:is(.active,.on,.selected,.is-active,[aria-pressed="true"],[aria-selected="true"],[data-selected],input:checked+*,label:has(input:checked)):not(#sheet){background:var(--main);color:var(--on-main);border-color:var(--main);animation:pick 160ms cubic-bezier(.34,1.56,.64,1)}
@keyframes pick{0%{transform:scale(1)}55%{transform:scale(1.06)}100%{transform:scale(1)}}
:where(p,li,td) a{display:inline!important;min-width:0!important;min-height:0!important;padding:0!important}
:where(div,section,article,aside,nav,header,footer,main,p,ul,ol,dl,pre,blockquote,fieldset,output):empty:not([role]):not([contenteditable]){display:none!important}
[hidden],input[type=hidden]{display:none!important}
.filepick{display:inline-flex;align-items:center;gap:12px;min-height:48px;padding:10px 20px;border-radius:10px!important;background:var(--main);color:var(--on-main);font-size:14px;font-weight:800;cursor:pointer;box-shadow:0 3px 0 color-mix(in srgb,#000 42%,var(--main));transition:transform var(--tap-out) var(--settle),box-shadow var(--tap-out) ease-out}
.filepick input[type=file]{position:absolute;width:1px;height:1px;opacity:0;pointer-events:none}
.filepick .filename{color:var(--on-main);font-size:13px;font-weight:500}

/* ===== 下のバーと、仮置きのシート ============================================
   ポケモンGO: 情報は上、親指は下。だから件数は下に置いたまま、
   **数字だけを大きくした**（20px/900）。ラベル「仮置き」は 11px＝数字の 55%。
   これは読ませる語ではない。数字だけが飛び込めばいい。 */
#fab{position:fixed;left:0;right:0;bottom:0;z-index:9;margin:0;display:flex;align-items:center;gap:8px;width:100%;min-height:60px;padding:12px 32px;text-align:left;background:var(--paper);color:var(--ink);border:0;border-radius:0!important;border-top:1px solid var(--rule);box-shadow:none;font-size:14px}
#fab:active{transform:none;filter:none;box-shadow:none;background:color-mix(in srgb,var(--ink) 6%,var(--paper))}
#fab .fabn{font-family:var(--num);font-size:20px;font-weight:900;line-height:1;font-variant-numeric:tabular-nums}
#fab .fabl{font-size:11px;font-weight:700;color:var(--muted);letter-spacing:.04em}
#fab::after{content:"▸";margin-left:auto;color:var(--muted)}
#sheet{display:none;position:fixed;inset:0;z-index:10;margin:0;background:color-mix(in srgb,var(--ink) 38%,transparent);color:var(--ink)}
#sheet.on{display:block}body:has(#sheet.on){overflow:hidden}
#sheet>div{position:absolute;right:0;top:0;bottom:0;width:min(704px,100%);margin:0;padding:0 32px 32px;overflow-y:auto;overscroll-behavior:contain;background:var(--paper);border-left:1px solid var(--rule)}
#sheet .sheet-head{position:sticky;top:0;z-index:1;display:flex;align-items:center;justify-content:space-between;gap:16px;margin:0;padding:16px 0;background:var(--paper);border-bottom:1px solid var(--rule)}
#sheet .sheet-head>*{margin:0}#sheet h2{font:800 23px/1.4 var(--ui)}
#sclose{border:0;border-radius:0!important;border-bottom:2px solid var(--ink);background:none;color:var(--ink);padding:8px 0;flex-shrink:0;box-shadow:none}
.as{margin-top:32px}.as>b{display:block;font:800 20px/1.6 var(--ui)}
.as .why{color:var(--muted);font-size:14px}
/* 赤は文字と帯だけ。面にしない。 */
.hi,.risk,.blank{color:var(--red)}.hi{font-size:14px;font-weight:800;font-variant-emoji:text}
@media(max-width:640px){body>header,main{padding:16px}main{padding-bottom:92px}h1{font-size:26px}.big{font-size:22px}#sheet>div{padding:0 16px 32px}#fab{padding:12px 16px}}
/* 動きは1か所で全部止まる。 */
@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important}}
"""

FRAME_JS = """
(function(){
var RM=matchMedia('(prefers-reduced-motion: reduce)').matches;
var TAP='button,[role=button],input[type=submit],input[type=button],input[type=reset],'+
        '.btn,.btn2,summary,[role=option],.filepick,label:has(input[type=radio]),'+
        'label:has(input[type=checkbox])';

/* 1. 押し返し。:active の戻りだけでは overshoot が出ない（移動量 6% のため）。
      離した瞬間に 180ms の keyframes を1本流す。クラス名に依存せず委譲で効かせる。 */
addEventListener('pointerup',function(e){
  if(RM) return;
  var b=e.target.closest&&e.target.closest(TAP);
  if(!b||b.id==='fab'||b.disabled) return;
  b.classList.remove('tapback'); void b.offsetWidth; b.classList.add('tapback');
  b.addEventListener('animationend',function(){b.classList.remove('tapback');},{once:true});
},true);

/* 2. 増えたものを見せる。モデルが何を書いても「押したら一覧が増えた」が目に見える。
      - 1度に 8件を超えたら動かさない（追加ではなく作り直しなので）
      - 同じ親は 400ms に1回まで（入力のたびに絞り込む画面でちらつかせない）
      ポケモンGO の「順次出現は 1件30msずらし、最大8件まで」を、teatime では
      40ms / 8件（ツムツムの連鎖 stagger と同値）に寄せた。 */
if(!RM&&window.MutationObserver){
  var queue=[], timer=null, last=new WeakMap();
  new MutationObserver(function(recs){
    for(var i=0;i<recs.length;i++){
      var r=recs[i];
      if(!r.addedNodes.length) continue;
      if(r.target.id==='sheet'||r.target.id==='fab') continue;
      for(var j=0;j<r.addedNodes.length;j++){
        var n=r.addedNodes[j];
        if(n.nodeType===1&&n.animate) queue.push(n);
      }
    }
    if(queue.length){clearTimeout(timer);timer=setTimeout(flush,0);}
  }).observe(document.body,{childList:true,subtree:true});
  function flush(){
    var nodes=queue.splice(0,queue.length);
    if(nodes.length>8) return;                 /* 作り直し。動かさない */
    var now=Date.now(), k=0;
    for(var i=0;i<nodes.length;i++){
      var el=nodes[i], p=el.parentNode;
      if(!el.isConnected||el.offsetParent===null) continue;
      if(p&&last.get(p)&&now-last.get(p)<400) continue;
      if(p) last.set(p,now);
      el.animate([{transform:'translateY(-10px) scale(.98)',opacity:0},
                  {transform:'none',opacity:1}],
                 {duration:220,delay:(k++)*40,
                  easing:'cubic-bezier(.2,.9,.3,1.15)',fill:'backwards'});
    }
  }
}

/* 3. 仮置きのシート。**出るときは勢いよく、閉じるときは目立たせず消す。**
      人は「出た」は見たいが「消えた」は見たくない。閉じに余韻があると
      「まだ終わっていない」と読まれる。
      横から出る面にオーバーシュートは掛けない——画面の端に隙間が開くため。 */
var fab=document.getElementById('fab'), sheet=document.getElementById('sheet');
if(fab&&sheet){
  var panel=sheet.firstElementChild;
  fab.onclick=function(){
    sheet.classList.add('on');
    if(RM) return;
    sheet.animate([{opacity:0},{opacity:1}],{duration:180,easing:'ease-out'});
    panel.animate([{transform:'translateX(100%)'},{transform:'none'}],
                  {duration:260,easing:'cubic-bezier(.16,1,.3,1)'});
  };
  var shut=function(){
    if(RM){sheet.classList.remove('on');return;}
    sheet.animate([{opacity:1},{opacity:0}],
                  {duration:140,easing:'cubic-bezier(.4,0,1,1)'})
         .onfinish=function(){sheet.classList.remove('on');};
  };
  sheet.onclick=function(e){if(e.target.id==='sheet'||e.target.id==='sclose')shut();};
}

/* 4. 選んだファイル名を出す。出さないと押した結果が分からない。 */
document.querySelectorAll('.filepick input[type=file]').forEach(function(i){
  i.onchange=function(){
    var n=i.parentNode.querySelector('.filename');
    if(n)n.textContent=i.files[0]?i.files[0].name:'';};
});
})();
"""


def _sheet(assumptions):
    # **外れると作り直す前提から読む。** 元の一覧は変更しない。
    ordered = sorted(assumptions, key=lambda a: a.get("risk") != "high")
    rows = []
    for a in ordered:
        hi = a.get("risk") == "high"
        rows.append(
            '<div class="as">'
            + ('<p class="hi">&#9873;&#65038; 高リスク</p>' if hi else '')
            + f'<b>{_h.escape(str(a.get("gap", "")))}</b>'
            f'<div>→ {_h.escape(str(a.get("assumption", "")))}</div>'
            f'<div class="why">なぜ: {_h.escape(str(a.get("why", "")))}'
            f'<br>確かめ方: {_h.escape(str(a.get("how_to_check", "")))}</div></div>')
    n = len(ordered)
    # **件数は数字だけが飛び込めばいい。** ラベル「仮置き」は数字の 55%・muted。
    return (
        '<button id="fab" type="button" aria-controls="sheet">'
        f'<span class="fabn">{n}</span><span class="fabl">仮置き</span></button>'
        '<div id="sheet"><div role="region" aria-labelledby="sheet-title">'
        '<div class="sheet-head"><h2 id="sheet-title">仮置き</h2>'
        '<button id="sclose" class="btn2" type="button">閉じる</button></div>'
        '<p class="mut">議論で決まっていないこと。作るために、いまは仮にこうしてあります。'
        '<span class="hi">&#9873;&#65038; 高リスク</span> は外れると作り直しになるもの。</p>'
        + "".join(rows) + '</div></div>')


def _clean(text, drop_tags=True):
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n", "", t).rsplit("```", 1)[0]
    if drop_tags:
        t = re.sub(r"</?(?:script|style)[^>]*>", "", t)
    return t.strip()


def _one_primary(markup):
    """**主ボタンは1つ。** [P01 一つの動詞を中心に置く]

    モデルに直させると、動いていた流れごと作り直して悪化する（実測 score -2 → -16）。
    **機械的に直せるものは機械で直す。** 最初の1つを残し、残りは副操作（btn2）に落とす。
    """
    seen = [False]

    def demote(m):
        classes = m.group(1).split()
        if "btn" not in classes:
            return m.group(0)
        if not seen[0]:
            seen[0] = True
            return m.group(0)
        return 'class="' + " ".join("btn2" if c == "btn" else c for c in classes) + '"'

    return re.sub(r'class="([^"]*)"', demote, markup)


def _jp_file(markup):
    """**ファイル選択の「Choose File」はCSSで変えられない。** 素の input を隠し、
    label をこちら側で書いて日本語のボタンにする。モデルの書き方に依存しない。"""
    def wrap(m):
        tag = m.group(0)
        if 'data-jp' in tag:
            return tag
        label = "写真を選ぶ" if re.search(r'accept=["\']?image', tag) else "ファイルを選ぶ"
        return (f'<label class="filepick">{label}'
                f'{tag[:-1]} data-jp>'
                f'<span class="filename"></span></label>')
    return re.sub(r'<input\b[^>]*type=["\']?file["\']?[^>]*>', wrap, markup, flags=re.I)


def _node():
    """node の居場所。**PATH に無くても、よくある置き場だけは見る。**"""
    for p in (shutil.which("node"), "~/.local/bin/node",
              "/opt/homebrew/bin/node", "/usr/local/bin/node"):
        if p:
            path = pathlib.Path(p).expanduser()
            if path.exists():
                return str(path)
    return None


def _js_check(js):
    """構文だけは機械に見させる。返すのは (状態, エラー文)。"""
    node = _node()
    if not node:
        return "skipped", ""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as f:
        f.write(js)
        path = pathlib.Path(f.name)
    try:
        out = subprocess.run([node, "--check", str(path)],
                             capture_output=True, text=True, timeout=60)
    finally:
        path.unlink(missing_ok=True)
    if out.returncode == 0:
        return "ok", ""
    return "ng", (out.stderr or out.stdout).strip()[:800]


FIX_PROMPT = """この画面は、機械の試験に落ちました。**落ちた所だけを直してください。**

## 落ちた観点
{failures}

## いまの画面
```html
{markup}
```

## 直し方の規則
- **構造で直す。** 「追加」「登録」「保存」「足す」のどれかを**文字として含むボタン**を置く。
  一覧は `<ul>` `<ol>` `<tbody>` のどれかにする。日付が要るなら `<input type="date">`。
- **押して何も起きないボタンを作らない。**
- **主ボタン（class="btn"）は画面に1つだけ。** その画面で一番やりたい動詞を1つ選ぶ。
  残りの操作は `class="btn2"` にする。入口で選ばせない。 押したら一覧か文言が**目に見えて変わる**こと。
- 画面の目的（{mvp}）を変えない。**落ちた所だけ**を直す。
- 使ってよい class は card row col btn btn2 mut tag big field のみ。

**HTML（画面の中身）だけ**を2500字以内で。説明を書かない。
"""


def _score(report):
    """**試験の良し悪しを1つの数にする。** skip は「その構造が無い」なので減点。"""
    s = (report or {}).get("summary") or {}
    return s.get("pass", 0) * 2 - s.get("fail", 0) * 3 - s.get("skip", 0)


def _failures(report):
    """落ちた観点と理由を、モデルに渡せる形にする。**pass は渡さない。**"""
    from . import uxcheck
    lines = []
    for key in uxcheck.IDS:
        c = (report.get("checks") or {}).get(key)
        if c and c["status"] in ("fail", "skip"):
            lines.append(f'- {uxcheck.LABELS[key]}（{c["status"]}）: '
                         + " ".join(c["reason"].split())[:160])
    return "\n".join(lines)


def _rounds():
    """**既定は1回だけ直す。** 直すたびに生成が1本増えるので、際限なく回さない。"""
    try:
        return max(0, min(3, int(os.environ.get("TEATIME_REFINE", "1"))))
    except ValueError:
        return 1


def refine(report, markup, mvp, assemble, on_step=None):
    """**作って終わりにしない。** 落ちた観点をモデルに返して作り直し、また測る。
    **良くなったときだけ採る**ので、直そうとして悪くなることが無い。"""
    from . import uxcheck
    best = {"markup": markup, "report": report, "score": _score(report)}
    history = [{"round": 0, "score": best["score"],
                "summary": dict((report or {}).get("summary") or {})}]
    for i in range(1, _rounds() + 1):
        failures = _failures(best["report"])
        if not failures:
            break  # **落ちていないなら触らない**
        if on_step:
            on_step(f"refine{i}")
        try:
            new_markup = _one_primary(_jp_file(_clean(model.ask(
                MARKUP_SYS, FIX_PROMPT.format(
                    failures=failures, markup=best["markup"], mvp=mvp)))))
            new_page = assemble(new_markup)
            new_report = uxcheck.check(new_page)
        except Exception as error:
            history.append({"round": i, "error": type(error).__name__})
            break
        new_score = _score(new_report)
        history.append({"round": i, "score": new_score,
                        "summary": dict(new_report.get("summary") or {}),
                        "採用": new_score > best["score"]})
        if new_score > best["score"]:
            best = {"markup": new_markup, "report": new_report, "score": new_score}
        else:
            break  # **良くならなかったら、そこで止める**
    return best, history


def build(transcript, structured, on_step=None):
    d = structured.get("decision") or {}
    sacrificed = "、".join(
        f'{a.get("sacrificed_value") or "?"}→{a.get("gained_value") or "?"}'
        for a in structured.get("abandonments", [])) or "（放棄は記録されていない）"
    core = json.dumps({"structured": deliver.for_document(structured), "transcript": transcript},
                      ensure_ascii=False)

    if on_step:
        on_step("assume")
    plan = model.ask_json(ASSUME_SYS, ASSUME_PROMPT.format(core=core))
    assumptions = plan.get("assumptions", [])
    mvp = plan.get("mvp") or "議論で出た一番小さい一本"

    if on_step:
        on_step("proto")
    markup = _clean(model.ask(MARKUP_SYS, MARKUP_PROMPT.format(
        mvp=mvp,
        adopted=d.get("adopted") or "（決まっていない。仮置きで進める）",
        condition=d.get("condition") or "（決まっていない。仮置きで進める）",
        sacrificed=sacrificed,
        assumptions=json.dumps(assumptions, ensure_ascii=False, indent=1),
        transcript=transcript[:6000])))  # **画面は考える工程**（決めたことを画面に訳す）。ローカルでは決定を落とした（2026-10-28）
    # **初回も refine も同じ手で絞る。** 片方だけに掛けると初回が素通りする
    markup = _one_primary(_jp_file(markup))

    def ask_js(role, err=""):
        prompt = JS_PROMPT.format(mvp=mvp, markup=markup)
        if err:
            prompt += JS_FIX_PROMPT.format(err=err)
        return _clean(model.ask(JS_SYS, prompt, role=role), drop_tags=True)

    js = ask_js("code")
    js_check, err = _js_check(js)
    if js_check == "ng":  # **直させる。** まず作る側、それでも駄目なら考える側
        js = ask_js("code", err)
        js_check, err = _js_check(js)
        if js_check == "ok":
            js_check = "retried"
    if js_check == "ng":
        js = ask_js("think", err)
        js_check, err = _js_check(js)
        if js_check == "ok":
            js_check = "claude"
    if js_check == "ng":
        # **壊れた JS はページに載せない。** 仮置きのボタンは別の JS なので生きる
        js, js_check = "", "failed"

    topic = structured.get("topic", "")

    def assemble(body):
        # **組み立ては1か所。** refine が同じ手で作り直せるようにする
        return (
            '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{_h.escape(mvp)[:40]}</title><style>{CSS}</style></head><body>"
            f'<header>プロトタイプ ・ 議論「{_h.escape(topic)}」から生成</header>'
            f"<main>{body}</main>"
            + _sheet(assumptions)
            + f"<script>{js}\n{FRAME_JS}</script></body></html>")

    page = assemble(markup)
    if on_step:
        on_step("uxcheck")
    try:
        from . import uxcheck
        report = uxcheck.check(page)
    except Exception as error:
        # **成果物は出す。試験の障害は隠さない。**
        report = {"checks": {}, "summary": {"fail": 0, "pass": 0, "skip": 0},
                  "execution": {"complete": False, "障害": type(error).__name__}}
    # **落ちたまま出さない。** 落ちた観点を返して作り直し、良くなったときだけ採る
    best, history = refine(report, markup, mvp, assemble, on_step)
    markup, report, page = best["markup"], best["report"], assemble(best["markup"])

    return {"mvp": mvp, "assumptions": assumptions, "html": page,
            "markup_chars": len(markup), "js_chars": len(js),
            "js_check": js_check, "ux": report, "refine": history}
