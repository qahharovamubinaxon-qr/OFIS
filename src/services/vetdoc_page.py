"""Дўкон маълумотномасининг очиқ саҳифаси — QR шу ерга олиб келади.

Саҳифа ўзи-ўзига етарли бир HTML файл: сервер ҳам, база ҳам керак эмас, шунчаки
турган жойидан очилади. Мижоз QR'ни сканерлаб, дўкон берган қоғоздаги
маълумотнинг ўша ёзувга мос келишини кўради.

Майдонлар реестрдаги кўринишнинг ҳаммаси: бўлимлар ҳам, тартиб ҳам ўша.
Тўлдирилмаган майдон барибир кўринади — офис кейинчалик реестрдан маълумот
олиб тўлдиради, саҳифанинг тузилиши эса ўзгармайди.

Юқориси ҳам ўша кўринишда: чапда логотип ва дўкон номи, ўнгда тил тугмалари
(РУС/ENG), дўкон тугмаси ва «Помощь»; остида текшириш варағи ва код бўйича
қидирув. Тил **ҳақиқатан** алмашади — ҳар ёрлиқнинг инглизчаси ўзи билан
юради, қийматлар эса оператор киритганича қолади.

Кўриниши атайин ДАВЛАТ тизиминики каби эмас: ўз ранги, ўз логотипи, ва пастда
«бу дўконнинг ўз маълумотномаси, давлат ВСД си эмас» деб очиқ ёзилган. Ҳужжат
ҳалол бўлиши — мижоз учун ҳам, дўкон учун ҳам шундай хавфсизроқ.
"""

from __future__ import annotations

from html import escape as _e

from src.domain.vetdoc import Shop, VetRecord

DOC_TITLE = "Справка о продаже и ветеринарной обработке животного"
DOC_TITLE_EN = "Certificate of sale and veterinary treatment of an animal"
#: Дўкон ранги. Эгаси реестрдаги каби тўқ қизилни танлади. Ранг ўзи ҳужжатни
#: давлатники қилиб қўймайди — логотип, ном, ҳужжат номи ва ҳар саҳифадаги
#: «бу дўконнинг ўз маълумотномаси» огоҳлантириши дўконники бўлиб қолади.
BRAND = "#8a2328"
BRAND_DARK = "#6f1b20"

DISCLAIMER_RU = ("Это <b>собственная справка магазина</b> о продаже и "
                 "ветеринарной обработке животного. Документ подтверждает "
                 "сведения, внесённые продавцом, и не является ветеринарным "
                 "сопроводительным документом (ВСД) государственной системы.")
DISCLAIMER_EN = ("This is the <b>shop's own certificate</b> of sale and "
                 "veterinary treatment of an animal. It confirms the details "
                 "entered by the seller and is not a state veterinary "
                 "accompanying document.")

_CSS = """
*{box-sizing:border-box}
body{margin:0;background:#f4f6f7;color:#243;font:14px/1.5 "Segoe UI",Arial,sans-serif}
.top{background:__DARK__;color:#fff;display:flex;align-items:stretch;
  min-height:46px;flex-wrap:wrap}
.top .mark{display:flex;align-items:center;gap:10px;padding:6px 16px}
.logo{width:26px;height:26px;border-radius:6px;background:#fff;color:__BRAND__;
  display:grid;place-items:center;font-weight:700;font-size:15px;flex:none;
  overflow:hidden}
.logo img{width:100%;height:100%;object-fit:contain}
.brand{font-size:17px;font-weight:600;letter-spacing:.4px;line-height:1.1}
.brand small{display:block;font-size:10.5px;font-weight:400;opacity:.8;
  letter-spacing:0}
.top .sp{flex:1}
.lang{display:flex}
.lang button,.tbtn{background:transparent;border:0;border-left:1px solid
  rgba(255,255,255,.18);color:#fff;padding:0 15px;font:inherit;font-size:12.5px;
  cursor:pointer;display:flex;align-items:center;gap:6px;text-decoration:none}
.lang button{padding:0 13px;opacity:.72}
.lang button.on{background:rgba(0,0,0,.22);opacity:1;font-weight:600}
.tbtn:hover,.lang button:hover{background:rgba(0,0,0,.14)}
.tabs{background:#fff;border-bottom:1px solid #dde3e3;display:flex;
  align-items:center;gap:10px;padding:0 16px;flex-wrap:wrap}
.tab{padding:11px 4px 9px;border-bottom:2px solid __BRAND__;color:__BRAND__;
  font-size:13px;font-weight:600;display:flex;align-items:center;gap:7px}
.tabs .sp{flex:1}
.find{display:flex;gap:0;margin:7px 0}
.find input{width:270px;max-width:46vw;padding:5px 10px;font-size:12.5px;
  border:1px solid #cfd8d8;border-right:0;border-radius:4px 0 0 4px}
.find button{background:#eef2f2;border:1px solid #cfd8d8;border-radius:0 4px 4px 0;
  padding:5px 12px;cursor:pointer;font-size:12.5px;color:#4a5a58}
.find button:hover{background:#e3eaea}
main{max-width:1180px;margin:0 auto;padding:10px 20px 40px}
.head{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;margin:14px 0 6px}
h1{font-size:22px;font-weight:400;color:#4b7f98;margin:0}
.head .sp{flex:1}
.print{background:none;border:0;color:#4b7f98;font:inherit;font-size:13px;
  cursor:pointer;padding:0}
.print:hover{text-decoration:underline}
h2{font-size:13px;font-weight:600;color:#6b7b7a;text-transform:uppercase;
  letter-spacing:.6px;margin:26px 0 8px;border-bottom:1px solid #dde3e3;padding-bottom:6px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:26px;align-items:start}
@media(max-width:860px){.cols{grid-template-columns:1fr}}
table{width:100%;border-collapse:collapse;background:#fff;
  border:1px solid #dde3e3;border-radius:4px;overflow:hidden}
tr+tr{border-top:1px solid #eef2f2}
th{width:42%;text-align:right;font-weight:400;color:#6b7b7a;background:#f7f9f9;
  padding:8px 12px;vertical-align:top}
td{padding:8px 12px;vertical-align:top}
.scroll{overflow-x:auto}
.grid{min-width:100%}
.grid th{width:auto;text-align:left;font-weight:600;color:#44524f;background:#f2f5f5;
  white-space:nowrap}
.grid td{white-space:nowrap}
.empty td{color:#9aa7a5;font-style:italic;white-space:normal}
.ok{display:inline-block;background:#d8efd8;color:#1d6b1d;border-radius:3px;
  padding:2px 9px;font-size:12px}
.code{font-family:Consolas,monospace;letter-spacing:1px}
footer{max-width:1180px;margin:0 auto;padding:16px 20px 40px;color:#7a8785;font-size:12px}
.note{background:#fff8e6;border:1px solid #f0e0b0;border-radius:5px;
  padding:10px 14px;color:#6b5b2a;font-size:12.5px;margin-top:22px}
dialog{border:1px solid #dde3e3;border-radius:8px;padding:0;max-width:560px;
  width:92vw;color:#243}
dialog::backdrop{background:rgba(10,30,28,.45)}
dialog .dh{background:__DARK__;color:#fff;padding:10px 16px;font-weight:600}
dialog .db{padding:14px 16px;font-size:13.5px}
dialog .db p{margin:0 0 10px}
dialog .dc{padding:0 16px 14px;text-align:right}
dialog .dc button{background:__BRAND__;color:#fff;border:0;border-radius:5px;
  padding:7px 18px;font:inherit;cursor:pointer}
@media print{.top,.tabs,.print,dialog{display:none}body{background:#fff}
  main{padding-top:0}}
""".replace("__BRAND__", BRAND).replace("__DARK__", BRAND_DARK)

_SCRIPT = """
function vetLang(code){
  document.querySelectorAll('[data-en]').forEach(function(node){
    if(node.dataset.ru===undefined){node.dataset.ru=node.textContent;}
    node.textContent = code==='en' ? node.dataset.en : node.dataset.ru;
  });
  document.querySelectorAll('[data-en-ph]').forEach(function(node){
    if(node.dataset.ruPh===undefined){node.dataset.ruPh=node.placeholder;}
    node.placeholder = code==='en' ? node.dataset.enPh : node.dataset.ruPh;
  });
  document.querySelectorAll('[data-en-html]').forEach(function(node){
    if(node.dataset.ruHtml===undefined){node.dataset.ruHtml=node.innerHTML;}
    node.innerHTML = code==='en' ? node.dataset.enHtml : node.dataset.ruHtml;
  });
  document.querySelectorAll('.lang button').forEach(function(btn){
    btn.classList.toggle('on', btn.dataset.lang===code);
  });
  document.documentElement.lang = code==='en' ? 'en' : 'ru';
  try{localStorage.setItem('vetdoc.lang', code);}catch(e){}
}
function vetHelp(){var d=document.getElementById('help'); if(d) d.showModal();}
function vetFind(event){
  event.preventDefault();
  var box=document.getElementById('code');
  var value=box ? box.value.trim().toUpperCase() : '';
  if(value){location.href=encodeURIComponent(value)+'.html';}
}
(function(){
  var saved='ru';
  try{saved=localStorage.getItem('vetdoc.lang')||'ru';}catch(e){}
  vetLang(saved);
})();
"""


def _t(ru: str, en: str) -> str:
    """Икки тилли ёрлиқ. Саҳифа русча очилади, ENG босилса инглизчага ўтади."""
    return f'<span data-en="{_e(en)}">{_e(ru)}</span>'


def _rows(pairs: list[tuple[str, str]]) -> str:
    """Бир жадвал: ёрлиқ (тайёр HTML) — қиймат.

    Бўш майдон ҳам кўрсатилади, реестрдаги кўриниш билан бир хил бўлсин: офис
    кейин тўлдиради, саҳифанинг тузилиши эса ҳар ёзувда ўзгармайди.
    """
    out = [f"<tr><th>{label}</th><td>{value or ''}</td></tr>"
           for label, value in pairs]
    return "<table>" + "".join(out) + "</table>"


def _wide(head: str, body: str, *, empty: str, empty_en: str,
          span: int) -> str:
    """Кенг жадвал — тор экранда ўзи сурилади."""
    if not body:
        body = (f'<tr class="empty"><td colspan="{span}">'
                f"{_t(empty, empty_en)}</td></tr>")
    return f'<div class="scroll"><table class="grid">{head}{body}</table></div>'


def _docs(record: VetRecord) -> str:
    head = ("<tr>"
            f"<th>{_t('Серия', 'Series')}</th>"
            f"<th>{_t('Номер', 'Number')}</th>"
            f"<th>{_t('Дата выдачи', 'Date of issue')}</th>"
            f"<th>{_t('Тип документа', 'Document type')}</th></tr>")
    body = "".join(
        f"<tr><td>{_e(d.series)}</td><td>{_e(d.number)}</td>"
        f"<td>{_e(d.issued)}</td><td>{_e(d.kind)}</td></tr>"
        for d in record.docs)
    return _wide(head, body, span=4,
                 empty="сопроводительные документы не указаны",
                 empty_en="no accompanying documents listed")


def _animals(record: VetRecord) -> str:
    head = ("<tr>"
            f"<th>{_t('№ п/п', 'No.')}</th>"
            f"<th>{_t('Номер животного/группы', 'Animal/group number')}</th>"
            f"<th>{_t('Номер средства маркирования', 'Marking device number')}</th>"
            f"<th>{_t('Внутрихозяйственный номер', 'On-farm number')}</th>"
            f"<th>{_t('Кличка', 'Name')}</th>"
            f"<th>{_t('Пол', 'Sex')}</th>"
            f"<th>{_t('Порода', 'Breed')}</th>"
            f"<th>{_t('Возраст', 'Age')}</th>"
            f"<th>{_t('Вес (кг)', 'Weight (kg)')}</th>"
            f"<th>{_t('Кол-во', 'Count')}</th>"
            f"<th>{_t('Примечание', 'Note')}</th></tr>")
    body = "".join(
        f"<tr><td>{i}</td><td>{_e(a.group_no)}</td><td>{_e(a.mark)}</td>"
        f"<td>{_e(a.farm_no)}</td><td>{_e(a.nickname)}</td><td>{_e(a.sex)}</td>"
        f"<td>{_e(a.breed)}</td><td>{_e(a.age)}</td><td>{_e(a.weight)}</td>"
        f"<td>{_e(a.count)}</td><td>{_e(a.note)}</td></tr>"
        for i, a in enumerate(record.animals, 1))
    return _wide(head, body, span=11, empty="животные не указаны",
                 empty_en="no animals listed")


def _treatments(record: VetRecord) -> str:
    head = ("<tr>"
            f"<th>{_t('Тип', 'Type')}</th>"
            f"<th>{_t('Наименование', 'Name')}</th>"
            f"<th>{_t('Дата проведения', 'Date')}</th>"
            f"<th>{_t('Название и производитель препарата', 'Drug and manufacturer')}</th>"
            f"<th>{_t('Номер серии препарата', 'Drug batch number')}</th>"
            f"<th>{_t('Действует до', 'Valid until')}</th></tr>")
    body = "".join(
        f"<tr><td>{_e(t.kind)}</td><td>{_e(t.name)}</td><td>{_e(t.done)}</td>"
        f"<td>{_e(t.drug)}</td><td>{_e(t.series)}</td><td>{_e(t.until)}</td></tr>"
        for t in record.treatments)
    return _wide(head, body, span=6, empty="обработка не проводилась",
                 empty_en="no treatment carried out")


def _chrome(shop: Shop, *, tab_ru: str, tab_en: str) -> str:
    """Юқори қатор: логотип, ном, тиллар, дўкон ва «Помощь» тугмалари."""
    name = shop.name or "ВЕТ-МАГАЗИН"
    mark = _e(name[:1].upper() or "В")
    site = (shop.site or "").strip()
    shop_button = ""
    if site:
        if not site.startswith(("http://", "https://")):
            site = "https://" + site
        shop_button = (f'<a class="tbtn" href="{_e(site)}">'
                       f"{_t('Магазин', 'Shop')}</a>")
    return f"""<header class="top">
  <div class="mark">
    <div class="logo">{mark}</div>
    <div class="brand">{_e(name)}
      <small>{_t('ветеринарный магазин · аптека',
                 'veterinary shop · pharmacy')}</small></div>
  </div>
  <div class="sp"></div>
  <div class="lang">
    <button type="button" class="on" data-lang="ru"
            onclick="vetLang('ru')">РУС</button>
    <button type="button" data-lang="en" onclick="vetLang('en')">ENG</button>
  </div>
  {shop_button}
  <button type="button" class="tbtn" onclick="vetHelp()">
    {_t('Помощь', 'Help')}</button>
</header>
<nav class="tabs">
  <span class="tab">✔ {_t(tab_ru, tab_en)}</span>
  <div class="sp"></div>
  <form class="find" onsubmit="vetFind(event)">
    <input id="code" maxlength="12" autocomplete="off"
           placeholder="поиск по коду справки"
           data-en-ph="search by certificate code"
           aria-label="Код справки">
    <button type="submit">🔍</button>
  </form>
</nav>"""


def _help_dialog(shop: Shop) -> str:
    contact = " · ".join(x for x in (shop.address, shop.phone) if x)
    return f"""<dialog id="help">
  <div class="dh">{_t('Помощь', 'Help')}</div>
  <div class="db">
    <p data-en-html="This page shows a certificate issued by the shop. Scan the
       QR code on the paper copy, or type its verification code above — the
       details on screen must match the paper.">Эта страница показывает справку,
       выданную магазином. Отсканируйте QR-код на бумажной справке или введите
       её код проверки в поле выше — сведения на экране должны совпадать с
       бумагой.</p>
    <p data-en-html="The certificate is the shop's own document. It is not a
       state veterinary accompanying document.">Справка является собственным
       документом магазина и не является ветеринарным сопроводительным
       документом государственной системы.</p>
    <p>{_e(contact)}</p>
  </div>
  <div class="dc"><button type="button"
    onclick="document.getElementById('help').close()">
    {_t('Закрыть', 'Close')}</button></div>
</dialog>"""


def _note() -> str:
    return (f'<div class="note" data-en-html="{_e(DISCLAIMER_EN)}">'
            f"{DISCLAIMER_RU}</div>")


def _footer(shop: Shop) -> str:
    name = shop.name or "ВЕТ-МАГАЗИН"
    tail = " · ".join(x for x in (shop.legal or name, shop.address, shop.phone)
                      if x)
    return f"<footer>{_e(tail)}</footer>"


def page_html(record: VetRecord, shop: Shop) -> str:
    """Битта ёзувнинг очиқ саҳифаси, ўзи-ўзига етарли HTML."""
    name = shop.name or "ВЕТ-МАГАЗИН"
    issued = record.issued.strftime("%d.%m.%Y") if record.issued else ""
    seller = shop.legal or name

    general = _rows([
        (_t("Статус", "Status"),
         f'<span class="ok">{_e(record.status)}</span>'),
        (_t("Номер справки", "Certificate number"),
         f"<b>{_e(record.number or record.code)}</b>"),
        (_t("Код проверки", "Verification code"),
         f'<span class="code">{_e(record.code)}</span>'),
        (_t("Уникальный идентификатор", "Unique identifier"),
         f'<span class="code">{_e(record.uid)}</span>'),
        (_t("Учёт", "Record keeping"), _e(record.accounting)),
        (_t("Дата оформления", "Date of issue"), _e(issued)),
        (_t("Наименование документа", "Document title"),
         _t(DOC_TITLE, DOC_TITLE_EN)),
        (_t("Способ оформления", "Issuing method"), _e(record.made_by)),
        (_t("Номер бланка", "Form number"), _e(record.blank_no)),
        (_t("Выдал", "Issued by"), _e(seller)),
    ])
    product = _rows([
        (_t("Номер производственной партии", "Production batch number"),
         _e(record.batch)),
        (_t("Тип продукции", "Product type"), _e(record.kind)),
        (_t("Продукция", "Product"), _e(record.product)),
        (_t("Вид продукции", "Product kind"), _e(record.species)),
        (_t("Наименование продукции", "Product name"), _e(record.title)),
        (_t("Объём", "Volume"), _e(record.volume)),
        (_t("Дата рождения", "Date of birth"), _e(record.birth)),
        (_t("Благополучие местности", "Area health status"),
         _e(record.wellbeing)),
        (_t("Направление", "Purpose"), _e(record.purpose)),
        (_t("Животные содержались", "Animals were kept"),
         _e(record.held_since)),
        (_t("Место для карантинирования", "Quarantine location"),
         _e(record.quarantine_place)),
        (_t("Количество дней карантинирования", "Quarantine days"),
         _e(record.quarantine_days)),
        (_t("Особые отметки", "Special notes"), _e(record.notes)),
        (_t("Номер и дата входящего документа",
            "Incoming document no. and date"), _e(record.incoming_doc)),
        (_t("Номер и дата производственного документа",
            "Production document no. and date"), _e(record.production_doc)),
        (_t("Примечание", "Remark"), _e(record.remark)),
    ])
    transport = _rows([
        (_t("Тип транзакции", "Transaction type"), _e(record.transaction)),
        (_t("Тип транспорта", "Transport type"), _e(record.transport)),
        (_t("Способ хранения при перевозке", "Storage during transport"),
         _e(record.storage)),
    ])
    issuing = _rows([
        (_t("Учреждение", "Institution"), _e(record.institution or seller)),
        (_t("Ф.И.О.", "Full name"), _e(record.vet_name)),
        (_t("Должность", "Position"), _e(record.vet_post)),
        (_t("Контактный телефон", "Contact phone"),
         _e(record.vet_phone or shop.phone)),
    ])
    origin = _rows([
        (_t("Страна происхождения", "Country of origin"),
         _e(record.origin_country)),
        (_t("Выработана / выращены", "Produced / raised by"),
         _e(record.produced_by)),
        (_t("Наименование продукции при производстве",
            "Product name at production"), _e(record.production_name)),
        (_t("Документ о происхождении", "Document of origin"),
         _e(record.origin_doc)),
    ])
    receiver = _rows([
        (_t("Название предприятия", "Company name"),
         _e(record.receiver_company)),
        (_t("Хозяйствующий субъект (владелец)", "Business entity (owner)"),
         _e(record.receiver_subject)),
        (_t("Покупатель", "Buyer"), _e(record.buyer)),
    ])
    sender = _rows([
        (_t("Название предприятия", "Company name"),
         _e(record.sender_company or seller)),
        (_t("Хозяйствующий субъект (владелец)", "Business entity (owner)"),
         _e(record.sender_subject)),
        (_t("Адрес", "Address"), _e(shop.address)),
        (_t("Телефон", "Phone"), _e(shop.phone)),
        (_t("ИНН", "Tax ID"), _e(shop.inn)),
    ])

    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>{_e(name)} — справка {_e(record.code)}</title>
<style>{_CSS}</style></head><body>
{_chrome(shop, tab_ru="Проверка справки", tab_en="Check certificate")}
<main>
  <div class="head">
    <h1>{_t('Просмотр информации о справке', 'Certificate details')}</h1>
    <div class="sp"></div>
    <button type="button" class="print" onclick="window.print()">
      🖨 {_t('Печать', 'Print')}</button>
  </div>

  <h2>{_t('Общие сведения', 'General information')}</h2>
  {general}

  <div class="cols">
    <div><h2>{_t('Информация о продукции', 'Product information')}</h2>
      {product}</div>
    <div>
      <h2>{_t('Сведения о транспорте', 'Transport details')}</h2>{transport}
      <h2>{_t('Сведения об оформлении', 'Issuing details')}</h2>{issuing}
    </div>
  </div>

  <h2>{_t('Сведения о происхождении продукции', 'Product origin')}</h2>
  {origin}

  <div class="cols">
    <div><h2>{_t('Сведения о получателе', 'Consignee')}</h2>{receiver}</div>
    <div><h2>{_t('Сведения об отправителе', 'Consignor')}</h2>{sender}</div>
  </div>

  <h2>{_t('Сведения о документах', 'Documents')}</h2>
  {_docs(record)}

  <h2>{_t('Опись живых животных', 'List of live animals')}</h2>
  {_animals(record)}

  <h2>{_t('Сведения об иммунизации и обработке против паразитов',
          'Immunisation and antiparasitic treatment')}</h2>
  {_treatments(record)}

  {_note()}
</main>
{_footer(shop)}
{_help_dialog(shop)}
<script>{_SCRIPT}</script>
</body></html>"""


def index_html(records: list[VetRecord], shop: Shop) -> str:
    """Дўкон саҳифаларининг рўйхати — код бўйича текшириш шу ерда.

    Мижоз QR'ни сканерлай олмаса, кодни юқоридаги қидирувга теради ва ўз
    ёзувига тушади. Қидириш саҳифанинг ўзида, браузерда ишлайди.
    """
    name = shop.name or "ВЕТ-МАГАЗИН"
    rows = []
    for record in records:
        issued = record.issued.strftime("%d.%m.%Y") if record.issued else ""
        title = record.title or record.product or record.kind
        rows.append(
            f'<tr><td><a href="{_e(record.code)}.html">{_e(record.code)}</a></td>'
            f"<td>{_e(record.number)}</td><td>{_e(issued)}</td>"
            f"<td>{_e(title)}</td><td>{_e(record.volume)}</td>"
            f"<td>{_e(record.buyer)}</td>"
            f'<td><span class="ok">{_e(record.status)}</span></td></tr>')
    head = ("<tr>"
            f"<th>{_t('Код', 'Code')}</th>"
            f"<th>{_t('Номер', 'Number')}</th>"
            f"<th>{_t('Дата', 'Date')}</th>"
            f"<th>{_t('Продукция', 'Product')}</th>"
            f"<th>{_t('Объём', 'Volume')}</th>"
            f"<th>{_t('Покупатель', 'Buyer')}</th>"
            f"<th>{_t('Статус', 'Status')}</th></tr>")
    table = _wide(head, "".join(rows), span=7, empty="записей пока нет",
                  empty_en="no records yet")

    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(name)} — проверка справок</title>
<style>{_CSS}
.list td{{white-space:normal}}
.list a{{color:{BRAND};font-weight:600;text-decoration:none}}
.list tr:hover td{{background:#f7faf9}}
</style></head><body>
{_chrome(shop, tab_ru="Проверка справки", tab_en="Check certificate")}
<main>
  <div class="head">
    <h1>{_t('Проверка справки', 'Certificate check')}</h1>
  </div>
  <p>{_t('Введите код с бумажной справки в поле поиска наверху — '
         'или отсканируйте QR-код на ней.',
         'Type the code from the paper certificate into the search box above '
         '— or scan the QR code on it.')}</p>

  <h2>{_t('Выданные справки', 'Issued certificates')}</h2>
  <div class="list">{table}</div>

  {_note()}
</main>
{_footer(shop)}
{_help_dialog(shop)}
<script>{_SCRIPT}</script>
</body></html>"""
