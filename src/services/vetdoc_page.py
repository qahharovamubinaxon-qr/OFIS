"""Дўкон маълумотномасининг очиқ саҳифаси — QR шу ерга олиб келади.

Саҳифа ўзи-ўзига етарли бир HTML файл: сервер ҳам, база ҳам керак эмас, шунчаки
турган жойидан очилади. Мижоз QR'ни сканерлаб, дўкон берган қоғоздаги
маълумотнинг ўша ёзувга мос келишини кўради.

Майдонлар реестрдаги кўринишнинг ҳаммаси: бўлимлар ҳам, тартиб ҳам ўша.
Тўлдирилмаган майдон барибир кўринади — офис кейинчалик реестрдан маълумот
олиб тўлдиради, саҳифанинг тузилиши эса ўзгармайди.

Кўриниши атайин ДАВЛАТ тизиминики каби эмас: ўз ранги, ўз логотипи, ва пастда
«бу дўконнинг ўз маълумотномаси, давлат ВСД си эмас» деб очиқ ёзилган. Ҳужжат
ҳалол бўлиши — мижоз учун ҳам, дўкон учун ҳам шундай хавфсизроқ.
"""

from __future__ import annotations

from html import escape as _e

from src.domain.vetdoc import Shop, VetRecord

DOC_TITLE = "Справка о продаже и ветеринарной обработке животного"
#: Дўкон ранги — давлат тизимининг тўқ қизилидан атайин бошқача.
BRAND = "#12605b"
BRAND_DARK = "#0d4b47"

_CSS = """
*{box-sizing:border-box}
body{margin:0;background:#f4f6f7;color:#243;font:14px/1.5 "Segoe UI",Arial,sans-serif}
header{background:__BRAND__;color:#fff;padding:10px 20px;display:flex;
  align-items:center;gap:12px;flex-wrap:wrap}
.logo{width:26px;height:26px;border-radius:6px;background:#fff;color:__BRAND__;
  display:grid;place-items:center;font-weight:700;font-size:15px;flex:none}
.brand{font-size:19px;font-weight:600;letter-spacing:.5px}
.brand small{display:block;font-size:11px;font-weight:400;opacity:.85;letter-spacing:0}
header .sp{margin-left:auto}
.btn{background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.35);
  color:#fff;border-radius:5px;padding:5px 12px;font-size:13px;cursor:pointer}
main{max-width:1180px;margin:0 auto;padding:18px 20px 40px}
h1{font-size:21px;font-weight:500;color:__BRAND__;margin:10px 0 18px}
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
@media print{header .sp,.btn{display:none}body{background:#fff}}
""".replace("__BRAND__", BRAND)


def _rows(pairs: list[tuple[str, str]]) -> str:
    """Бир жадвал: майдон номи — қиймати.

    Бўш майдон ҳам кўрсатилади, реестрдаги кўриниш билан бир хил бўлсин: офис
    кейин тўлдиради, саҳифанинг тузилиши эса ҳар ёзувда ўзгармайди.
    """
    out = [f"<tr><th>{_e(str(label))}</th><td>{value or ''}</td></tr>"
           for label, value in pairs]
    return "<table>" + "".join(out) + "</table>"


def _wide(head: str, body: str, *, empty: str, span: int) -> str:
    """Кенг жадвал — тор экранда ўзи сурилади."""
    if not body:
        body = f'<tr class="empty"><td colspan="{span}">{_e(empty)}</td></tr>'
    return f'<div class="scroll"><table class="grid">{head}{body}</table></div>'


def _docs(record: VetRecord) -> str:
    head = ("<tr><th>Серия</th><th>Номер</th><th>Дата выдачи</th>"
            "<th>Тип документа</th></tr>")
    body = "".join(
        f"<tr><td>{_e(d.series)}</td><td>{_e(d.number)}</td>"
        f"<td>{_e(d.issued)}</td><td>{_e(d.kind)}</td></tr>"
        for d in record.docs)
    return _wide(head, body, span=4,
                 empty="сопроводительные документы не указаны")


def _animals(record: VetRecord) -> str:
    head = ("<tr><th>№ п/п</th><th>Номер животного/группы</th>"
            "<th>Номер средства маркирования</th>"
            "<th>Внутрихозяйственный номер</th><th>Кличка</th><th>Пол</th>"
            "<th>Порода</th><th>Возраст</th><th>Вес (кг)</th>"
            "<th>Кол-во</th><th>Примечание</th></tr>")
    body = "".join(
        f"<tr><td>{i}</td><td>{_e(a.group_no)}</td><td>{_e(a.mark)}</td>"
        f"<td>{_e(a.farm_no)}</td><td>{_e(a.nickname)}</td><td>{_e(a.sex)}</td>"
        f"<td>{_e(a.breed)}</td><td>{_e(a.age)}</td><td>{_e(a.weight)}</td>"
        f"<td>{_e(a.count)}</td><td>{_e(a.note)}</td></tr>"
        for i, a in enumerate(record.animals, 1))
    return _wide(head, body, span=11, empty="животные не указаны")


def _treatments(record: VetRecord) -> str:
    head = ("<tr><th>Тип</th><th>Наименование</th><th>Дата проведения</th>"
            "<th>Название и производитель препарата</th>"
            "<th>Номер серии препарата</th><th>Действует до</th></tr>")
    body = "".join(
        f"<tr><td>{_e(t.kind)}</td><td>{_e(t.name)}</td><td>{_e(t.done)}</td>"
        f"<td>{_e(t.drug)}</td><td>{_e(t.series)}</td><td>{_e(t.until)}</td></tr>"
        for t in record.treatments)
    return _wide(head, body, span=6, empty="обработка не проводилась")


def page_html(record: VetRecord, shop: Shop) -> str:
    """Битта ёзувнинг очиқ саҳифаси, ўзи-ўзига етарли HTML."""
    name = shop.name or "ВЕТ-МАГАЗИН"
    issued = record.issued.strftime("%d.%m.%Y") if record.issued else ""
    mark = _e(name[:1].upper() or "В")
    seller = shop.legal or name

    general = _rows([
        ("Статус", f'<span class="ok">{_e(record.status)}</span>'),
        ("Номер справки", f"<b>{_e(record.number or record.code)}</b>"),
        ("Код проверки", f'<span class="code">{_e(record.code)}</span>'),
        ("Уникальный идентификатор", f'<span class="code">{_e(record.uid)}</span>'),
        ("Учёт", _e(record.accounting)),
        ("Дата оформления", _e(issued)),
        ("Наименование документа", _e(DOC_TITLE)),
        ("Способ оформления", _e(record.made_by)),
        ("Номер бланка", _e(record.blank_no)),
        ("Выдал", _e(seller)),
    ])
    product = _rows([
        ("Номер производственной партии", _e(record.batch)),
        ("Тип продукции", _e(record.kind)),
        ("Продукция", _e(record.product)),
        ("Вид продукции", _e(record.species)),
        ("Наименование продукции", _e(record.title)),
        ("Объём", _e(record.volume)),
        ("Дата рождения", _e(record.birth)),
        ("Благополучие местности", _e(record.wellbeing)),
        ("Направление", _e(record.purpose)),
        ("Животные содержались", _e(record.held_since)),
        ("Место для карантинирования", _e(record.quarantine_place)),
        ("Количество дней карантинирования", _e(record.quarantine_days)),
        ("Особые отметки", _e(record.notes)),
        ("Номер и дата входящего документа", _e(record.incoming_doc)),
        ("Номер и дата производственного документа", _e(record.production_doc)),
        ("Примечание", _e(record.remark)),
    ])
    transport = _rows([
        ("Тип транзакции", _e(record.transaction)),
        ("Тип транспорта", _e(record.transport)),
        ("Способ хранения при перевозке", _e(record.storage)),
    ])
    issuing = _rows([
        ("Учреждение", _e(record.institution or seller)),
        ("Ф.И.О.", _e(record.vet_name)),
        ("Должность", _e(record.vet_post)),
        ("Контактный телефон", _e(record.vet_phone or shop.phone)),
    ])
    origin = _rows([
        ("Страна происхождения", _e(record.origin_country)),
        ("Выработана / выращены", _e(record.produced_by)),
        ("Наименование продукции при производстве", _e(record.production_name)),
        ("Документ о происхождении", _e(record.origin_doc)),
    ])
    receiver = _rows([
        ("Название предприятия", _e(record.receiver_company)),
        ("Хозяйствующий субъект (владелец)", _e(record.receiver_subject)),
        ("Покупатель", _e(record.buyer)),
    ])
    sender = _rows([
        ("Название предприятия", _e(record.sender_company or seller)),
        ("Хозяйствующий субъект (владелец)", _e(record.sender_subject)),
        ("Адрес", _e(shop.address)),
        ("Телефон", _e(shop.phone)),
        ("ИНН", _e(shop.inn)),
    ])

    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>{_e(name)} — справка {_e(record.code)}</title>
<style>{_CSS}</style></head><body>
<header>
  <div class="logo">{mark}</div>
  <div class="brand">{_e(name)}<small>ветеринарный магазин · аптека</small></div>
  <div class="sp"></div>
  <button class="btn" onclick="window.print()">Печать</button>
</header>
<main>
  <h1>Проверка справки № {_e(record.number or record.code)}</h1>

  <h2>Общие сведения</h2>
  {general}

  <div class="cols">
    <div><h2>Информация о продукции</h2>{product}</div>
    <div>
      <h2>Сведения о транспорте</h2>{transport}
      <h2>Сведения об оформлении</h2>{issuing}
    </div>
  </div>

  <h2>Сведения о происхождении продукции</h2>
  {origin}

  <div class="cols">
    <div><h2>Сведения о получателе</h2>{receiver}</div>
    <div><h2>Сведения об отправителе</h2>{sender}</div>
  </div>

  <h2>Сведения о документах</h2>
  {_docs(record)}

  <h2>Опись живых животных ({record.head_count()})</h2>
  {_animals(record)}

  <h2>Сведения об иммунизации и обработке против паразитов</h2>
  {_treatments(record)}

  <div class="note">
    Это <b>собственная справка магазина</b> о продаже и ветеринарной обработке
    животного. Документ подтверждает сведения, внесённые продавцом, и не является
    ветеринарным сопроводительным документом (ВСД) государственной системы.
  </div>
</main>
<footer>{_e(seller)}{' · ' + _e(shop.address) if shop.address else ''}
{' · ' + _e(shop.phone) if shop.phone else ''}</footer>
</body></html>"""


_INDEX_CSS = _CSS + """
.find{display:flex;gap:8px;margin:14px 0 6px;flex-wrap:wrap}
.find input{flex:1;min-width:200px;padding:8px 11px;border:1px solid #cfd8d8;
  border-radius:5px;font-size:14px}
.find button{background:__BRAND__;color:#fff;border:0;border-radius:5px;
  padding:8px 18px;font-size:14px;cursor:pointer}
.list td{white-space:normal}
.list a{color:__BRAND__;font-weight:600;text-decoration:none}
.list tr:hover td{background:#f7faf9}
.none{color:#8a9593;padding:14px 2px}
""".replace("__BRAND__", BRAND)


def index_html(records: list[VetRecord], shop: Shop) -> str:
    """Дўкон саҳифаларининг рўйхати — код бўйича текшириш шу ерда.

    Мижоз QR'ни сканерлай олмаса, кодни шу ерга теради ва ўз ёзувига тушади.
    Қидириш саҳифанинг ўзида, браузерда ишлайди: сервер керак эмас.
    """
    name = shop.name or "ВЕТ-МАГАЗИН"
    mark = _e(name[:1].upper() or "В")
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
    body = "".join(rows) or (
        '<tr><td colspan="7" class="none">записей пока нет</td></tr>')

    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(name)} — проверка справок</title>
<style>{_INDEX_CSS}</style></head><body>
<header>
  <div class="logo">{mark}</div>
  <div class="brand">{_e(name)}<small>ветеринарный магазин · аптека</small></div>
</header>
<main>
  <h1>Проверка справки</h1>
  <p>Введите код с бумажной справки — или отсканируйте QR-код на ней.</p>
  <form class="find" onsubmit="go(event)">
    <input id="code" placeholder="например, A7K2M9" autocomplete="off"
           maxlength="12" aria-label="Код справки">
    <button type="submit">Проверить</button>
  </form>

  <h2>Выданные справки</h2>
  <div class="scroll"><table class="grid list">
    <tr><th>Код</th><th>Номер</th><th>Дата</th><th>Продукция</th>
        <th>Объём</th><th>Покупатель</th><th>Статус</th></tr>
    {body}
  </table></div>

  <div class="note">
    Справки на этой странице — <b>собственные документы магазина</b> о продаже и
    ветеринарной обработке животных. Они не являются ветеринарными
    сопроводительными документами (ВСД) государственной информационной системы.
  </div>
</main>
<footer>{_e(shop.legal or name)}{' · ' + _e(shop.address) if shop.address else ''}
{' · ' + _e(shop.phone) if shop.phone else ''}</footer>
<script>
function go(e){{
  e.preventDefault();
  var v=document.getElementById('code').value.trim().toUpperCase();
  if(v) location.href=encodeURIComponent(v)+'.html';
}}
</script>
</body></html>"""
