# Academic-Reading — starter corpus

**37 texts, ready to use.** German 11, French 8, Italian 10, Chinese 8.
Each is a coherent excerpt of roughly 1000 words that stands on its own as an
argument, not the first 1000 words of a longer thing.

```
texts/
  manifest.json      <- read this from the app
  sources.json       <- provenance: where each text came from
  modernise_de.py    <- the German orthography rules that were applied
  de/  de-01.txt … de-11.txt
  fr/  fr-01.txt … fr-09.txt
  it/  it-01.txt … it-10.txt
  zh/  zh-01.txt … zh-09.txt
```

`manifest.json` is what the app should load. Each entry carries `id`, `lang`,
`author`, `title`, `year`, `topic`, `copyright`, `file`, `length`,
`length_unit`, a one-line `excerpt` description of which passage was taken, and
for Chinese `script` and `register`.

## What was done to the texts

**Excerpting.** Passage boundaries were chosen by reading each text, not by
counting words from the top. Every excerpt starts and ends on a sentence
boundary. Where a famous passage was the point of including the text, the
excerpt contains it — Bismarck's *"Wir Deutsche fürchten Gott, sonst nichts auf
der Welt"*, Weber's *"dennoch!"*, Renan's *plébiscite de tous les jours*, Zola's
anaphora, Simmel on Blasiertheit.

**German orthography** normalised to current spelling across all eleven texts:
`Theil`→`Teil`, `giebt`→`gibt`, `daß`→`dass`, `muß`/`mußte`→`muss`/`musste`,
`-iren`→`-ieren`, `Bedürfniß`→`Bedürfnis`. The rules live in `modernise_de.py`
and are guarded against the obvious traps (`Rathaus`, `rothaarig`, `Gastwirt`,
`die Iren` are left alone).

**Chinese character sets**, 50:50 as agreed:

| | texts | script | register |
|---|---|---|---|
| `zh-01`–`zh-05` | Wei Yuan, Yan Fu, Liang Qichao, Cai Yuanpei | traditional | 文言文 → transitional |
| `zh-06`–`zh-09` | Li Dazhao, Hu Shi, Sun Yat-sen, Fei Xiaotong | simplified | 白話文 |

Conversion used OpenCC. Note the boundary does double duty: it is also the
classical/vernacular divide. A student choosing a traditional text is choosing a
much harder one, and the UI should say so rather than leaving it as a hidden
correlation.

**Cleanup.** OCR hyphenation rejoined, footnote markers stripped, PDF running
heads removed, whitespace normalised, everything NFC-normalised UTF-8.

## Five texts were dropped

| id | text | why |
|---|---|---|
| `de-12` | Habermas, *Strukturwandel der Öffentlichkeit* | not obtained |
| `fr-02` | Proudhon, *Idée générale de la Révolution* | download produced an empty file |
| `fr-10` | Bourdieu, *Sur la télévision* | not obtained |
| `zh-04` | 陳獨秀, 敬告青年 | the Wikisource search resolved to the *New Youth* tables of contents, not the essay |
| `zh-10` | 邓小平, 解放思想，实事求是 | not obtained |

The file delivered as `fr-10.pdf` turned out to be *Le Deuxième Sexe*, so it
became `fr-09` (Beauvoir) and Bourdieu is the one that went missing.

Proudhon and Chen Duxiu are the two worth chasing — both are pivotal and both
are firmly public domain. Chen Duxiu's 敬告青年 in particular leaves the Chinese
set without its New Culture Movement manifesto.

## One text is short

`it-05` (Mosca, *Elementi di scienza politica*) is **620 words**, not ~1000. The
only transcription available breaks off part-way through chapter I. It is
coherent as far as it goes and worth keeping for the elite-theory pairing with
Pareto, but the app should not assume a uniform length.

## Copyright

32 texts are `PD` — public domain worldwide. Five are `FD` — Adorno,
Weizsäcker, Beauvoir, Eco, Fei Xiaotong — and each is a single ~1000-word
excerpt used under educational fair dealing. The `copyright` field in `manifest.json` marks which
is which, so the distinction stays visible if the corpus is ever redistributed.
