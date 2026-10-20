# qa — daily-use QA battery

What an ordinary user does with the camera every day, one item per operation.
Run the set against a firmware build and read the verdict per item: PASS, FAIL
or NOT_EXERCISED. A surface the run did not reach is NOT_EXERCISED and never
PASS, and the item says what would reach it.

```sh
python3 verify/qa/z8qa.py run --observations <dir> --out qa-out --build <build>
```

One command, one report: `qa-out/qa-report.md` plus `qa-report.json`.

| Surface | Items |
|---|---|
| power | power on, power off, sleep and wake, battery level |
| shooting | P/A/S/M modes, single and continuous and self-timer, half press and full release |
| exposure | exposure compensation, ISO, white balance |
| live view | streaming frames, flip screen |
| playback | enter, zoom, protect, delete, slideshow, histogram |
| recording | record start and stop |
| menus | browsing, quality, focus mode, metering, colour, sound, brightness, date and time |
| cards | swap, dual card, card full, format |
| usb | connect and release |
| errors | shutter without a card, power on without a battery |

Each item is an operation sequence, the behaviour to expect and the rule that
judges it. Judgement is dynamic: the rule reads what the run recorded. Sessions
come from any driver that writes the observation schema; see `z8qa.py`.

```sh
python3 verify/qa/z8qa.py selftest
```

Selftest proves the rules separate a passing item from a failing one and that
missing input never passes.
