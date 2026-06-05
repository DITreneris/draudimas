# Ataskaita: viesiejipirkimai.lt stebejimo agentas

| | |
|---|---|
| **Klientas** | UAB Rizikos Cesija |
| **Data** | 2026-05-20 |
| **Laikotarpis** | nuo sistemos paleidimo (2026-04-23) iki ataskaitos datos |
| **Saltiniai** | GitHub `items.json`, Railway veiklos logai (2026-05-08–05-15), viešas dashboard |

---

## Santrauka

Automatinis agentas **darbo dienomis kas valanda (7:00–21:00, Vilniaus laikas)** tikrina [viesiejipirkimai.lt](https://viesiejipirkimai.lt) pagal raktinius zodzius **„draudim“** ir **„kasko“**, fiksuoja **naujus** viešuosius pirkimus ir juos pateikia per pranesimus bei vieša lentele.

| Rodiklis | Reiksme |
|----------|---------|
| Unikaliu pirkimu duomenu bazeje | **40** |
| Nauju pirkimu po stebejimo pradzios (nuo 2026-05-08) | **21** |
| Paiesku sekmingumas (8 d. logu langas) | **~93 %** |
| Eksporto i GitHub klaidos | **0** |
| Kritiniai gedimai (crash / restart) | **0** |

**Isvada:** sistema veikia **stabiliai**; aptikti pirkimai kaupiami ir prieinami klientui realiu laiku. Retos nesekmes susijusios su **laikinais portalo sutrikimais**, ne su agento architektura.

---

## Ka veikia agentas

1. **Paieska** — portale ieskoma pagal konfiguruotus raktinius zodzius (iki 50 rezultatu vienam zodziui).
2. **Atranka** — naujas skelbimas = naujas **Pirkimo ID** (dublikatai nepranesami).
3. **Pranesimai** — konsolė / logas; papildomai Telegram ir el. pastas (jei ijungta).
4. **Ataskaita klientui** — duomenys eksportuojami i vieša lentele (GitHub Pages).

**Grafikas:** pirmadienis–penktadienis, **15 patikrinimu per diena** (kas valanda 7–21 val.).

---

## Surinkti duomenys (2026-05-20)

Paskutinis duomenu atnaujinimas: **2026-05-20, 04:00 UTC** (07:00 Lietuvos laiku).

### Bendra statistika

| Metrika | Skaicius |
|---------|----------|
| Is viso unikaliu pirkimu | **40** |
| Pagal raktažodi „draudim“ | **32** (80 %) |
| Pagal raktažodi „kasko“ | **8** (20 %) |

### Pirkimu tipai (pagal pavadinima)

| Tipas | Kiekis | Dalis |
|-------|--------|-------|
| Draudimo pirkimai (standartiniai) | 36 | 90 % |
| Rinkos konsultacijos | 3 | 7,5 % |
| Draudimo brokerio paslaugos | 1 | 2,5 % |

### Nauji pirkimai stebejimo metu

**2026-05-07** — pradinis uzpildymas: fiksuoti jau portale matomi skelbimai (**19** irasu).

**Nuo 2026-05-08** agentas aptiko **21 nauja** unikalu pirkima:

| Data (aptikimo) | Nauju pirkimu |
|-----------------|---------------|
| 2026-05-08 | 1 |
| 2026-05-11 | 2 |
| 2026-05-12 | 4 |
| 2026-05-13 | 4 |
| 2026-05-14 | 1 |
| 2026-05-15 | 4 |
| 2026-05-18 | 3 |
| 2026-05-19 | 2 |
| **Is viso** | **21** |

*Vidutinis intensyvumas: apie **2 nauji pirkimai per darbo diena**.*

### Paskutiniai 5 aptikti pirkimai

| Pirkimo ID | Trumpas aprasymas | Perkanti organizacija |
|------------|-------------------|------------------------|
| 7933912 | Laivu CA draudimo pirkimo spec. projektas | Klaipedos juru uosto direkcija |
| 7929520 | TP privalomasis ir kasko draudimas | UAB Kauno vandenys |
| 7915385 | TP atsakomybe, Kasko, DNAS draudimas | Rokiskio r. savivaldybe |
| 7890120 | TP privalomasis ir kasko draudimas | UAB Kauno vandenys |
| 7891964 | Turto draudimas | AB „Miesto gijos“ |

---

## Sistemos patikimumas

Duomenys is Railway serverio logu (**2026-05-08 – 2026-05-15**, ~8 darbo dienu):

| Metrika | Reiksme |
|---------|---------|
| Atlikti ciklai (pradeti ir baigti) | **68** |
| Sekmingi duomenu eksportai i GitHub | **69** |
| Eksporto klaidos | **0** |
| Sekmingos keyword paieskos | **~128** |
| Nesekmingos paieskos | **~9** |
| **Paiesku sekmingumas** | **~93 %** (nesekme **~7 %**) |
| Ciklai, kuriu metu rasti nauji pirkimai | **10** (~15 % visu ciklu) |
| Crash / atminties / restart klaidos | **0** |

**2026-05-13** — viena problemingesne diena: laikini portalo sutrikimai (puslapio neikrovimas). Kita diena veikimas atsistate. Veliau idiegtas **automatinis pakartotinis bandymas** (iki 3 kartu), kad sumazinti tokiu atveju poveiki.

---

## Kur perziureti rezultatus

| Paskirtis | Nuoroda |
|-----------|---------|
| **Vieša lentele** (paieska, filtrai, atnaujinimas kas 60 s) | https://ditreneris.github.io/draudimas/ |
| **Duomenu failas** (JSON) | https://github.com/DITreneris/draudimas/blob/main/docs/items.json |

Lenteleje matomi: Pirkimo ID, pavadinimas, vykdytojas (organizacija), klase (draudikas / brokeris / rinkos konsultacija), raktazodis, paskelbimo ir aptikimo datos.

---

## Apribojimai (svarbu klientui)

- Stebimi tik skelbimai, atitinkantys raktinius zodzius **„draudim“** ir **„kasko“**.
- Nuskaitomas **tik pirmas** rezultatu puslapis (iki 50 irasu vienam zodziui).
- Tas pats pirkimas pranesamas **viena karta**, net jei atitinka abu zodzius.
- Pradiniame paleidime visi matomi skelbimai uzfiksuojami kaip „nauji“ — todel **2026-05-07** skaicius didesnis nei veliau.

---

## Rekomenduojamos tolesnes veiklos kryptys

1. Periodiskai perziureti [vieša lentele](https://ditreneris.github.io/draudimas/) ir naujus pranesimus (Telegram / el. pastas).
2. Prireikus papildyti raktinius zodzius (pvz. `civilin`, `turto`) — konfiguracija keiciama be kodo pakeitimu.
3. Ilgalaikėje perspektyvoje — periodine si ataskaitos forma (kas menesi ar ketvirti).

---

*Ataskaita parengta automatizuotai pagal agento sukauptus duomenis ir serverio veiklos logus. Klausimams — kreiptis i sistemos administratoriu.*
