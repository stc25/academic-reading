# Academic Reading — v2

A reading-skills tutor for academic texts in any language. Everything the app
says is in English, whatever the text is written in.

## How this differs from v1

| | v1 | v2 |
|---|---|---|
| Languages | German, French, Italian, Chinese | any |
| App's own language | English or the target language, per activity | English throughout |
| Reader's level | declared in the sidebar | not asked; the **text** carries a level |
| Texts | 37 bundled, `manifest.json` | none bundled; whatever is in `sources/` |
| Model routing | one model per language, all four listed | a default, plus per-language exceptions |
| Formats | `.txt` | `.txt`, `.md` |

The ten activities are the same, and so is the two-column layout.

## Running it

```bash
uv run streamlit run app.py
```

Put `OLLAMA_API_KEY` in `.env` to use the cloud backend, or switch to Local in
the sidebar's Model panel and run Ollama yourself.

## Adding texts

Drop `.txt` or `.md` files into `sources/`. That is enough — a file with no
catalogue entry is still offered, titled from its filename with its language
guessed. Describe it in `source.cfg` to do better:

```ini
[marx]
title    = Manifest der Kommunistischen Partei — I. Bourgeois und Proletarier
author   = Karl Marx & Friedrich Engels, 1848
language = German
file     = marx-manifest.txt
level    = advanced
source   = https://www.marxists.org/deutsch/...
notes    = Opening of section I. Orthography modernised.
```

One section per text; the section name is the id and is never shown. Every
field is optional:

| field | what it does |
|---|---|
| `title` | what the reader sees. Defaults to the filename. |
| `author` | who wrote it, and the date if known — `Jules Ferry, 1885`. Shown as a byline and passed to the model as provenance. `by` also works. |
| `language` | English name or ISO code. Detected from the text if absent. |
| `file` | the file in `sources/`. Defaults to `<section>.txt`. `FILE-NAME`, `file_name` and `filename` also work. |
| `level` | `introductory`, `intermediate`, `advanced`, or a CEFR band. Sets how much the model explains. Defaults to `default_level` in `config.yaml`. |
| `source` | provenance, shown under the text. |
| `notes` | a line on what this passage is. |

A named file that is missing is reported in the sidebar, not fatal.

### Author, and the absence of a year field

There is no separate `year`: put the date in `author`, as `Jules Ferry, 1885`.
The whole string is passed through as provenance, so the model reads the date
either way, and one field is easier to leave blank than two.

Leave `author` out rather than guess at it. House rule 1 forbids the model from
inventing an author, and the metadata note tells it that a name is not a date —
so an omitted author costs activities 1, 7 and 8 a little reach (no period
placement, no "written for this occasion") but never produces a fabricated one.
An author with no date is fine and is treated the same way.

### Length

Texts are expected to be 400–2000 words, times 1.6 for languages written
without spaces. Outside that they still open, with a warning: too short and the
activities have little to work with, too long and the end of the text starts
falling out of the model's context.

### Markdown

`.md` files are reduced to plain prose at load — headings lose their `#`, links
keep their text, code fences are dropped. Markdown is not *rendered*, because
the reading pane builds its own HTML so that close commentary can anchor notes
at character offsets in the body. That only works if what the reader sees and
what the model was given are the same string.

## Configuring models

`config.yaml`, per backend: a `default` for everything, and `by_language` for
the exceptions. Keys may be an ISO code or an English language name — both are
matched — so a text in a language named nowhere just gets the default.

```yaml
cloud:
  default: gemma4:31b
  by_language:
    zh: gpt-oss:120b
    Latin: gpt-oss:120b
```

## Levels

The level belongs to the text and is read as *the level of reader this text is
meant for*: an introductory text is explained generously, an advanced one
sparingly. If you would rather it meant "this text is hard, so help more",
swap the `introductory` and `advanced` blocks under `level_guidance` in
`prompts.yaml`. Nothing in the code depends on the direction.

## Editing prompts

`prompts.yaml` is re-read on every generation, so an edit takes effect on the
next Generate without restarting. An activity declares which turns it has by
which templates it defines — `user`, `brief`, `feedback` — and any other key in
its block becomes a `${placeholder}`, resolved per level if it is a mapping.

## Language detection

Only ever a suggestion. `langdetect` covers 55 languages and does not include
Latin, Ancient Greek or Old English, so it will confidently mislabel them —
which is why `source.cfg` states the language outright and the upload panel
offers a language chooser. Chinese, Japanese and Korean are decided by script
rather than by langdetect, which cannot tell classical Chinese from Japanese in
a passage light on kana.
