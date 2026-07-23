# OFIS — Windows'da ishga tushirish va EXE yasash

## 1. Talablar
- **Windows 10/11**
- **Python 3.12+** — [python.org/downloads](https://www.python.org/downloads/) dan yuklang.
  O'rnatishda **"Add Python to PATH"** katakchasini belgilang.

## 2. Kodni olish
GitHub'da `qahharovamubinaxon-qr/OFIS` → yashil **Code** → **Download ZIP** →
papkaga chiqaring. (Yoki `git clone https://github.com/qahharovamubinaxon-qr/OFIS.git`)

## 3. Ishga tushirish (dastur)
PowerShell yoki CMD ni OFIS papkasi ichida oching:

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m src.app
```

Birinchi `pip install` ~3–5 daqiqa (PySide6 katta). Keyin oyna ochiladi.

### Dastur qanday ishlaydi
1. **Process** ekrani ochiladi. Firmani tanlang (ИП ГОРДИЕНКО oldindan bor).
2. **Sana** va **Должность** ni tanlang (bo'sh = ПОДСОБНЫЙ РАБОЧИЙ).
3. **AI bilan:** Паспорт va Патент rasmlarini yuklang → **RUN**. (Avval
   Sozlamalarga Gemini kalitini kiriting.)
4. **AI'siz:** **«Qo'lda to'ldirish»** → 16 maydonli jadvalni to'ldiring → PDF.
5. PDF `output\<firma>\<FAMILIYA>.pdf` ga saqlanadi. Reg № avtomatik oshadi.
6. **Arxiv / Qidiruv** — barcha yaratilgan PDF'lar; ochish uchun ikki marta bosing.

### Gemini kaliti (AI uchun)
[aistudio.google.com/apikey](https://aistudio.google.com/apikey) dan bepul
kalit oling → dasturda **Sozlamalar → Gemini API kalit** ga qo'ying → Saqlash.

## 4. EXE yasash (tarqatish uchun)
```
.venv\Scripts\activate
pip install pyinstaller
pyinstaller build\ofis.spec
```
Natija: `dist\OFIS\OFIS.exe` — butun papkani ko'chirib, boshqa kompyuterda
Python'siz ishlatsa bo'ladi. Ma'lumotlar (sozlama, output, arxiv)
`%LOCALAPPDATA%\OFIS` da saqlanadi.

## Eslatma
- Matn **Calibri** shriftida yoziladi (Windows'da tizim Calibri, aks holda
  bir xil o'lchamli Carlito).
- Yangi firma qo'shish: **Firmalar → + Yangi firma** → ma'lumot + bo'sh shablon
  PDF. Barcha shablonlar bir xil katak koordinatasiga ega, kod o'zgarmaydi.
